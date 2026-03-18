"""Mortal inference engine.

Adapted from MahjongCopilot/bot/local/engine.py - inference only.
Loads model weights and provides MortalEngine for libriichi.mjai.Bot.
"""

import torch
import numpy as np
from torch.distributions import Normal, Categorical
from ai.mortal_model import Brain, DQN


class MortalEngine:
    def __init__(self, brain, dqn, *, is_oracle, version,
                 device=None, stochastic_latent=False, enable_amp=False,
                 enable_quick_eval=True, enable_rule_based_agari_guard=False,
                 name='NoName', boltzmann_epsilon=0, boltzmann_temp=1, top_p=1):
        self.engine_type = 'mortal'
        self.device = device or torch.device('cpu')
        self.brain = brain.to(self.device).eval()
        self.dqn = dqn.to(self.device).eval()
        self.is_oracle = is_oracle
        self.version = version
        self.stochastic_latent = stochastic_latent
        self.enable_amp = enable_amp
        self.enable_quick_eval = enable_quick_eval
        self.enable_rule_based_agari_guard = enable_rule_based_agari_guard
        self.name = name
        self.boltzmann_epsilon = boltzmann_epsilon
        self.boltzmann_temp = boltzmann_temp
        self.top_p = top_p

    def react_batch(self, obs, masks, invisible_obs):
        with (
            torch.autocast(self.device.type, enabled=self.enable_amp),
            torch.no_grad(),
        ):
            return self._react_batch(obs, masks, invisible_obs)

    def _react_batch(self, obs, masks, invisible_obs):
        obs = torch.as_tensor(np.stack(obs, axis=0), device=self.device)
        masks = torch.as_tensor(np.stack(masks, axis=0), device=self.device)
        invisible_obs = None
        if self.is_oracle:
            invisible_obs = torch.as_tensor(
                np.stack(invisible_obs, axis=0), device=self.device)
        batch_size = obs.shape[0]

        match self.version:
            case 1:
                mu, logsig = self.brain(obs, invisible_obs)
                if self.stochastic_latent:
                    latent = Normal(mu, logsig.exp() + 1e-6).sample()
                else:
                    latent = mu
                q_out = self.dqn(latent, masks)
            case 2 | 3 | 4:
                phi = self.brain(obs)
                q_out = self.dqn(phi, masks)

        if self.boltzmann_epsilon > 0:
            is_greedy = torch.full(
                (batch_size,), 1 - self.boltzmann_epsilon,
                device=self.device).bernoulli().to(torch.bool)
            logits = (q_out / self.boltzmann_temp).masked_fill(~masks, -torch.inf)
            sampled = _sample_top_p(logits, self.top_p)
            actions = torch.where(is_greedy, q_out.argmax(-1), sampled)
        else:
            is_greedy = torch.ones(batch_size, dtype=torch.bool, device=self.device)
            actions = q_out.argmax(-1)

        return actions.tolist(), q_out.tolist(), masks.tolist(), is_greedy.tolist()


def _sample_top_p(logits, p):
    if p >= 1:
        return Categorical(logits=logits).sample()
    if p <= 0:
        return logits.argmax(-1)
    probs = logits.softmax(-1)
    probs_sort, probs_idx = probs.sort(-1, descending=True)
    probs_sum = probs_sort.cumsum(-1)
    mask = probs_sum - probs_sort > p
    probs_sort[mask] = 0.
    return probs_idx.gather(-1, probs_sort.multinomial(1)).squeeze(-1)


def get_engine(model_file: str) -> MortalEngine:
    """Load Mortal model weights and create inference engine."""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    state = torch.load(model_file, map_location=device, weights_only=False)

    config = state['config']
    version = config['control']['version']
    conv_channels = config['resnet']['conv_channels']
    num_blocks = config['resnet']['num_blocks']

    brain = Brain(conv_channels=conv_channels, num_blocks=num_blocks,
                  is_oracle=False, version=version).eval()
    dqn = DQN(version=version).eval()
    brain.load_state_dict(state['mortal'])
    dqn.load_state_dict(state['current_dqn'])

    return MortalEngine(
        brain, dqn,
        is_oracle=False, device=device, enable_amp=False,
        enable_quick_eval=False, enable_rule_based_agari_guard=False,
        name='mortal', version=version,
    )
