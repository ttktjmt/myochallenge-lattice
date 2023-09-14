import numpy as np
from myosuite.envs.myo.reach_v0 import ReachEnvV0
from envs.env_mixins import DictObsMixin, ObsEmbeddingMixin
from definitions import ACT_KEY, GOAL_KEY


class MuscleReachEnv(ReachEnvV0, DictObsMixin, ObsEmbeddingMixin):
    OBS_KEYS = [ACT_KEY, GOAL_KEY]

    def __init__(
        self,
        model_path,
        obsd_model_path=None,
        seed=None,
        include_adapt_state=False,
        num_memory_steps=30,
        **kwargs
    ):
        self._init_done = False
        super().__init__(
            model_path=model_path, obsd_model_path=obsd_model_path, seed=seed, **kwargs
        )
        self.action_dim = self.sim.model.nu
        self._dict_obs_init_addon(include_adapt_state, num_memory_steps)
        self._obs_embedding_init_addon()
        self._init_done = True

    def _setup(
        self,
        target_reach_range: dict,
        far_th=0.35,
        obs_keys: list = OBS_KEYS,
        weighted_reward_keys: dict = ReachEnvV0.DEFAULT_RWD_KEYS_AND_WEIGHTS,
        **kwargs
    ):
        super()._setup(
            target_reach_range, far_th, obs_keys, weighted_reward_keys, **kwargs
        )
        self.obs_keys.remove("act")
    
    def reset(self):
        super().reset()
        obs = self.create_history_reset_state(self.obs_dict)
        obs = self.add_positions_to_obs(obs)
        return obs
    
    def step(self, action):
        obs, reward, done, info = super().step(action)
        info.update(info.get("rwd_dict"))
        if self._init_done:
            obs = self.create_history_reset_state(self.obs_dict)
            obs = self.add_positions_to_obs(obs)
        return obs, reward, done, info
    
    def get_obs_dict(self, sim):
        obs_dict = super().get_obs_dict(sim)
        obs_dict["muscle_len"] = np.nan_to_num(sim.data.actuator_length.copy())
        obs_dict["muscle_vel"] = np.nan_to_num(sim.data.actuator_velocity.copy())
        obs_dict["muscle_force"] = np.nan_to_num(sim.data.actuator_force.copy())
        
        muscle_keys = ("muscle_len", "muscle_vel", "muscle_force", "act")
        obs_dict["actuator_obs"] = np.row_stack(
            [obs_dict[key] for key in muscle_keys]
        )  # num_channels * num_actuators
        
        goal_keys = ("reach_err",)
        # num_channels * num_goals = 1 * 15
        obs_dict["goal_obs"] = np.row_stack([obs_dict[key] for key in goal_keys])
        return obs_dict
    
    def get_obs_elements(self):
        actuators = list(self.sim.model.actuator_names)
        objects = []
        goals = []
        for target in self.target_reach_range.keys():
            goals.extend([f"{target}_x", f"{target}_y", f"{target}_z"])
        return [*actuators, *objects, *goals]