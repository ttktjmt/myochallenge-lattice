import numpy as np
import collections
import gym
from myosuite.envs.myo.myochallenge.chasetag_v0 import ChaseTagEnvV0, ChallengeOpponent
from myosuite.envs.myo.base_v0 import BaseV0
from myosuite.utils.quat_math import quat2euler


class CustomChallengeOpponent(ChallengeOpponent):
    def __init__(
        self,
        sim,
        rng,
        probabilities,
        min_spawn_distance,
        opponent_x_range,
        opponent_y_range,
        opponent_orient_range,
    ):
        self.x_min, self.x_max = opponent_x_range
        self.y_min, self.y_max = opponent_y_range
        self.theta_min, self.theta_max = opponent_orient_range
        if self.x_min > self.x_max:
            raise ValueError("Invalid x range:", self.x_min, self.x_max)
        if self.y_min > self.y_max:
            raise ValueError("Invalid y range:", self.y_min, self.y_max)
        if self.theta_min > self.theta_max:
            raise ValueError("invalid theta range:", self.theta_min, self.theta_max)
        max_distance = np.linalg.norm(
            (
                max(abs(self.x_min), abs(self.x_max)),
                max(abs(self.y_min), abs(self.y_max)),
            )
        )
        if max_distance <= min_spawn_distance:
            raise ValueError(
                "The provided spawn ranges are incompatible with the min spawn distance",
                opponent_x_range,
                opponent_y_range,
                min_spawn_distance,
            )
        super().__init__(
            sim=sim,
            rng=rng,
            probabilities=probabilities,
            min_spawn_distance=min_spawn_distance,
        )

    def reset_opponent(self):
        """
        This function should initially place the opponent on a random position with a
        random orientation with a minimum radius to the model.
        """
        self.opponent_vel = np.zeros((2,))
        self.sample_opponent_policy()
        dist = 0
        while dist < self.min_spawn_distance:
            pose = [
                self.rng.uniform(self.x_min, self.x_max),
                self.rng.uniform(self.y_min, self.y_max),
                self.rng.uniform(self.theta_min, self.theta_max),
            ]
            dist = np.linalg.norm(pose[:2] - self.sim.data.body("root").xpos[:2])
        if self.opponent_policy == "static_stationary":
            pose[:] = [0, -5, 0]
        self.set_opponent_pose(pose)
        self.opponent_vel[:] = 0.0


class CustomChaseTagEnv(ChaseTagEnvV0):
    CUSTOM_RWD_KEYS_AND_WEIGHTS = {
        "done": 0,
        "act_reg": 0,
        "lose": -10,
        "sparse": 0,
        "solved": 1,
        "alive": 1,
        "distance": 0,
        "vel_reward": 0,
        "cyclic_hip": 0,
        "ref_rot": 0,
        "joint_angle_rew": 0,
        "early_solved": 0,
        "joints_in_range": 0,
        "heel_pos": 0
    }

    CUSTOM_DEFAULT_OBS_KEYS = [
        'internal_qpos',
        'internal_qvel',
        'grf',
        'torso_angle',
        'opponent_pose',
        'opponent_vel',
        'model_root_pos',
        'model_root_vel',
        'muscle_length',
        'muscle_velocity',
        'muscle_force',
        # 'gait_phase', # added to improve loco better loco
        # 'feet_rel_positions'
    ]

    def __init__(self, model_path, obsd_model_path=None, seed=None, **kwargs):
        # This flag needs to be here to prevent the simulation from starting in a done state
        # Before setting the key_frames, the model and opponent will be in the cartesian position,
        # causing the step() function to evaluate the initialization as "done".
        self.startFlag = False

        # EzPickle.__init__(**locals()) is capturing the input dictionary of the init method of this class.
        # In order to successfully capture all arguments we need to call gym.utils.EzPickle.__init__(**locals())
        # at the leaf level, when we do inheritance like we do here.
        # kwargs is needed at the top level to account for injection of __class__ keyword.
        # Also see: https://github.com/openai/gym/pull/1497
        gym.utils.EzPickle.__init__(self, model_path, obsd_model_path, seed, **kwargs)

        # This two step construction is required for pickling to work correctly. All arguments to all __init__
        # calls must be pickle friendly. Things like sim / sim_obsd are NOT pickle friendly. Therefore we
        # first construct the inheritance chain, which is just __init__ calls all the way down, with env_base
        # creating the sim / sim_obsd instances. Next we run through "setup"  which relies on sim / sim_obsd
        # created in __init__ to complete the setup.
        BaseV0.__init__(
            self, model_path=model_path, obsd_model_path=obsd_model_path, seed=seed
        )
        self._setup(**kwargs)

    def _setup(
        self,
        obs_keys: list = CUSTOM_DEFAULT_OBS_KEYS,
        weighted_reward_keys: dict = CUSTOM_RWD_KEYS_AND_WEIGHTS,
        opponent_probabilities=[0.1, 0.45, 0.45],
        reset_type="none",
        win_distance=0.5,
        min_spawn_distance=2,
        max_time=20,
        min_height=0,
        stop_on_win=True,
        hip_period=100,
        opponent_x_range=(-5, 5),
        opponent_y_range=(-5, 5),
        opponent_orient_range=(-2 * np.pi, 2 * np.pi),
        gait_cadence=1.0,
        gait_stride_length=0.8,
        target_speed=0,
        **kwargs,
    ):
        self.gait_cadence = gait_cadence
        self.gait_stride_length = gait_stride_length
        self.target_speed = target_speed
        super()._setup(
            obs_keys=obs_keys,
            weighted_reward_keys=weighted_reward_keys,
            opponent_probabilities=opponent_probabilities,
            reset_type=reset_type,
            win_distance=win_distance,
            min_spawn_distance=min_spawn_distance,
            min_height=min_height,
            hip_period=hip_period,
            **kwargs,
        )
        self.opponent = CustomChallengeOpponent(
            sim=self.sim,
            rng=self.np_random,
            probabilities=opponent_probabilities,
            min_spawn_distance=min_spawn_distance,
            opponent_x_range=opponent_x_range,
            opponent_y_range=opponent_y_range,
            opponent_orient_range=opponent_orient_range,
        )
        self.maxTime = max_time
        self.stop_on_win = stop_on_win
        
    def reset(self):
        self.steps = 0
        obs = super().reset()
        return np.nan_to_num(obs)
    
    def get_obs_dict(self, sim):
        obs_dict = {}

        # Time
        obs_dict['time'] = np.array([sim.data.time])

        # proprioception
        obs_dict['internal_qpos'] = sim.data.qpos[7:35].copy()
        obs_dict['internal_qvel'] = sim.data.qvel[6:34].copy() * self.dt
        obs_dict['grf'] = self._get_grf().copy()
        obs_dict['torso_angle'] = self.sim.data.body('pelvis').xquat.copy()

        obs_dict['muscle_length'] = self.muscle_lengths()
        obs_dict['muscle_velocity'] = self.muscle_velocities()
        obs_dict['muscle_force'] = self.muscle_forces()

        if sim.model.na>0:
            obs_dict['act'] = sim.data.act[:].copy()

        # exteroception
        obs_dict['opponent_pose'] = self.opponent.get_opponent_pose()[:].copy()
        obs_dict['opponent_vel'] = self.opponent.opponent_vel[:].copy()
        obs_dict['model_root_pos'] = sim.data.qpos[:2].copy()
        obs_dict['model_root_vel'] = sim.data.qvel[:2].copy()

        # obs_dict['gait_phase'] = self.get_gait_phase()
        obs_dict['gait_phase'] = np.array([sim.data.time*self.gait_cadence % 1])

        # Get the feet positions relative to the pelvis. (f_l, f_r)
        obs_dict['feet_rel_positions'] = self._get_feet_relative_position()
        # phase between 0 and 1. If hip period is in same unit as steps then phase no units
        # obs_dict['phase_var'] = np.array([(self.steps/self.hip_period) % 1]).copy()

        return obs_dict

    def get_reward_dict(self, obs_dict):
        act_mag = (
            np.linalg.norm(self.obs_dict["act"], axis=-1).item() / self.sim.model.na
            if self.sim.model.na != 0
            else 0
        )
        win_cdt = self._win_condition()
        lose_cdt = self._lose_condition()
        score = self._get_score(float(self.obs_dict["time"])) if win_cdt else 0
        vel_reward = self._get_vel_reward()
        cyclic_hip = self._get_cyclic_rew()
        ref_rot = self._get_ref_rotation_rew()
        joint_angle_rew = self._get_joint_angle_rew(
            ["hip_adduction_l", "hip_adduction_r", "hip_rotation_l", "hip_rotation_r"]
        )

        rwd_dict = collections.OrderedDict(
            (
                # Perform reward tuning here --
                # Update Optional Keys section below
                # Update reward keys (DEFAULT_RWD_KEYS_AND_WEIGHTS) accordingly to update final rewards
                # Examples: Env comes pre-packaged with two keys act_reg and lose
                # Optional Keys
                ("act_reg", act_mag),
                ("lose", lose_cdt),
                ("distance", np.exp(-self.get_distance_from_opponent())),
                ("alive", not self._get_done()),
                ("vel_reward", vel_reward),
                ("cyclic_hip", np.exp(-cyclic_hip)),
                ("ref_rot", ref_rot),
                ("joint_angle_rew", joint_angle_rew),
                ("early_solved", win_cdt * (self.maxTime - self.obs_dict["time"]).item()),
                ("joints_in_range", self._frac_joints_in_range()),
                ("heel_pos", np.exp(- 4 * self._get_heel_rew())), # add factor of 4 bcs max value of dis is approx 1

                # Must keys
                ("sparse", score),
                ("solved", win_cdt),
                ("done", self._get_done()),
            )
        )
        rwd_dict["dense"] = np.sum(
            [wt * rwd_dict[key] for key, wt in self.rwd_keys_wt.items()], axis=0
        )
        # Success Indicator
        self.sim.model.site_rgba[self.success_indicator_sid, :] = (
            np.array([0, 2, 0, 0.1]) if rwd_dict["solved"] else np.array([2, 0, 0, 0])
        )
        return rwd_dict

    def get_distance_from_opponent(self):
        root_pos = self.sim.data.body("pelvis").xpos[:2]
        opp_pos = self.obs_dict["opponent_pose"][..., :2]
        return np.linalg.norm(root_pos - opp_pos)

    def step(self, action):
        obs, reward, done, info = super().step(action)
        obs = np.nan_to_num(obs)
        reward = np.nan_to_num(reward)
        info.update(info.get("rwd_dict"))
        return obs, reward, done, info

    def _lose_condition(self):
        fallen = self._get_height() < self.min_height
        episode_over = float(self.obs_dict["time"]) >= self.maxTime
        root_pos = self.sim.data.body('pelvis').xpos[:2]
        out_of_grid = (np.abs(root_pos[0]) > 6.5 or np.abs(root_pos[1]) > 6.5)
        return fallen or episode_over or out_of_grid

    def _get_done(self):
        if self._lose_condition():
            return 1
        if self._win_condition() and self.stop_on_win:
            return 1
        return 0
    
    def get_root_orientation(self):
        quat = self.sim.data.qpos[3:7].copy()
        xy_angle = quat2euler(quat)[-1]
        return np.array((np.cos(xy_angle), np.sin(xy_angle)))

    def get_opponent_relative_orientation(self):
        root_pos = self.sim.data.body("pelvis").xpos[:2].copy()
        opp_pos = self.obs_dict["opponent_pose"][..., :2].copy()
        dist_versor = opp_pos - root_pos
        versor_norm = np.linalg.norm(dist_versor)
        if versor_norm > 0:
            dist_versor /= versor_norm
        return dist_versor

    def _get_ref_rotation_rew(self):
        """
        Incentivize orienting the root towards the target.
        """
        root_rot = self.get_root_orientation()
        opponent_rot = self.get_opponent_relative_orientation()
        return np.exp(- 5. * np.linalg.norm(root_rot - opponent_rot))
    
    def _frac_joints_in_range(self):
        joints_lower_bound = self.joint_ranges[:, 0] <= self.sim.data.qpos[7:35]
        joints_upper_bound = self.sim.data.qpos[7:35] <= self.joint_ranges[:, 1]
        joints_in_range = np.logical_and(joints_lower_bound, joints_upper_bound)
        return np.mean(joints_in_range)

    @property
    def joint_ranges(self):
        return self.sim.model.jnt_range[1:, :].copy()

    def _get_heel_target(self):
        """
        Returns desired rel position of foot (rel to pelvis) during gait
        """
        phase = self.obs_dict["gait_phase"]
        # if 0. <= phase <= 0.5: # swing of right leg
        #     l_des = - self.gait_stride_length * (1/4 - phase)
        #     r_des = self.gait_stride_length * (1/4 - phase)
        # else: # swing of left leg
        #     l_des = - self.gait_stride_length * (phase - 3/4)
        #     r_des = self.gait_stride_length * (phase - 3/4)
        # return np.array([l_des, r_des])
        heel_pos = np.array([self.gait_stride_length * np.cos(phase * 2 * np.pi + np.pi), self.gait_stride_length* np.cos(phase * 2 * np.pi)], dtype=np.float32)
        return heel_pos
        

    def _get_heel_rew(self):
        """
        Relative heel position in gait rewarded to incentivize a walking gait.
        max distance is stride
        """
        l_heel, r_heel = self._get_feet_relative_position()
        des = self._get_heel_target()
        l_des = des[0]
        r_des = des[1]

        return np.linalg.norm(l_heel - l_des) + np.linalg.norm(r_heel - r_des) 

    def _get_vel_reward(self):
        """
        Gaussian that incentivizes a walking velocity. Going
        over only achieves flat rewards. 
        If both target vel are zero, follow a target speed set by gait
        """
        vel = self._get_com_velocity()

        # Check if both target velocities are zero
        if self.target_speed!=0:
            # Only compute the reward for a target speed (scalar)
            # target_speed = self.gait_cadence * self.gait_stride_length
            return np.exp(-np.square(self.target_speed - np.linalg.norm(vel)))

        # Compute the reward for both x and y velocities
        return np.exp(-np.square(self.target_y_vel - vel[1])) + np.exp(-np.square(self.target_x_vel - vel[0]))