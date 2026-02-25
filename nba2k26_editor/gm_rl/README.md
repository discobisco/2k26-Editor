# gm_rl folder

## Responsibilities
- GM RL env, policy, training/eval runtime, and action/feature modules.
- Integrated subsystem for the editor's GM Agent page (not a standalone program).
- Owns direct Python files: `__init__.py`, `actions.py`, `env.py`, `eval.py`, `features.py`, `models.py`, `ppo.py`, `runtime.py`, `train.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
GM RL env, policy, training/eval runtime, and action/feature modules.
This folder currently has 9 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- UI agent workflows in `nba2k_editor/ui/app.py` call into this runtime.
- Adapters and CBA subfolders provide data and legality constraints.

## Function Tree
Scope: direct Python files in this folder only. Child folder details are documented in their own READMEs.

### `__init__.py`
- No callable definitions.

### `actions.py`
  - [def] actions.py::ActionSpaceSpec.sizes
  - [def] actions.py::ActionMask.to
  - [def] actions.py::ActionMaskBuilder.__init__
  - [def] actions.py::ActionMaskBuilder._record_block
  - [def] actions.py::ActionMaskBuilder._record_warn
  - [def] actions.py::ActionMaskBuilder._citation_ids
  - [def] actions.py::ActionMaskBuilder.build
  - [def] actions.py::ActionGrammar.__init__
  - [def] actions.py::ActionGrammar.decode
  - [def] actions.py::ActionGrammar._rotation_template
  - [def] actions.py::ActionGrammar._cheapest_player
  - [def] actions.py::ActionGrammar._trade_pool
  - [def] actions.py::ActionGrammar._contract_pool
  - [def] actions.py::ActionGrammar._roster_move
  - [def] actions.py::ActionGrammar._first_true_index

### `env.py`
  - [def] env.py::MultiDiscrete.__init__
  - [def] env.py::Box.__init__
  - [def] env.py::NBA2KGMEnv.__init__
  - [def] env.py::NBA2KGMEnv.reset
  - [def] env.py::NBA2KGMEnv.step
  - [def] env.py::NBA2KGMEnv._to_obs_dict
  - [def] env.py::NBA2KGMEnv._episode_length
  - [def] env.py::NBA2KGMEnv._build_action_mask
  - [def] env.py::NBA2KGMEnv._compute_reward
  - [def] env.py::NBA2KGMEnv._player_value
  - [def] env.py::SyncVecEnv.__init__
  - [def] env.py::SyncVecEnv.num_envs
  - [def] env.py::SyncVecEnv.reset
  - [def] env.py::SyncVecEnv.step
  - [def] env.py::SyncVecEnv._stack
- [def] env.py::make_vec_env

### `eval.py`
- [def] eval.py::build_adapter
- [def] eval.py::evaluate
- [def] eval.py::main

### `features.py`
  - [def] features.py::ObservationBatch.to_torch
  - [def] features.py::RunningMeanStd.__init__
  - [def] features.py::RunningMeanStd.update
  - [def] features.py::RunningMeanStd.normalize
  - [def] features.py::FeatureEncoder.__init__
  - [def] features.py::FeatureEncoder.encode
  - [def] features.py::FeatureEncoder._team_features
  - [def] features.py::FeatureEncoder._league_features
  - [def] features.py::FeatureEncoder._player_table
  - [def] features.py::FeatureEncoder._team_dim
  - [def] features.py::FeatureEncoder._league_dim
  - [def] features.py::FeatureEncoder._player_dim
  - [def] features.py::FeatureEncoder._player_row
  - [def] features.py::FeatureEncoder._opt_val
  - [def] features.py::FeatureEncoder._encode_division
  - [def] features.py::FeatureEncoder._encode_conference

### `models.py`
  - [def] models.py::MaskedCategorical.__init__
  - [def] models.py::MaskedCategorical.entropy
  - [def] models.py::AttentionPool.__init__
  - [def] models.py::AttentionPool.forward
  - [def] models.py::GMPolicy.__init__
  - [def] models.py::GMPolicy.forward
  - [def] models.py::GMPolicy.act

### `ppo.py`
  - [def] ppo.py::RolloutBuffer.__init__
  - [def] ppo.py::RolloutBuffer.add
  - [def] ppo.py::RolloutBuffer.compute_returns_and_advantages
  - [def] ppo.py::RolloutBuffer.get_batches
  - [def] ppo.py::RolloutBuffer.reset
  - [def] ppo.py::PPOTrainer.__init__
  - [def] ppo.py::PPOTrainer._stack_action_masks
  - [def] ppo.py::PPOTrainer.train
  - [def] ppo.py::PPOTrainer._mask_list_from_info
  - [def] ppo.py::PPOTrainer._log_metrics
  - [def] ppo.py::PPOTrainer.save_checkpoint

### `runtime.py`
  - [def] runtime.py::AgentRuntime.__init__
  - [def] runtime.py::AgentRuntime.events
  - [def] runtime.py::AgentRuntime.stop
  - [def] runtime.py::AgentRuntime.start_evaluate
  - [def] runtime.py::AgentRuntime.start_live_assist
  - [def] runtime.py::AgentRuntime.start_training
  - [def] runtime.py::AgentRuntime._mask_from_info
    - [def] runtime.py::AgentRuntime._mask_from_info._to_mask
  - [def] runtime.py::AgentRuntime._run_evaluate
  - [def] runtime.py::AgentRuntime._run_live_assist
  - [def] runtime.py::AgentRuntime._run_training

### `train.py`
- [def] train.py::set_seed
- [def] train.py::load_config
- [def] train.py::save_config
- [def] train.py::build_adapter
- [def] train.py::main
  - [def] train.py::main.env_fn

## Child Folder Map
- `adapters/`: `adapters/README.md`
- `cba/`: `cba/README.md`

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
