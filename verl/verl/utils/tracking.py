# Copyright 2024 Bytedance Ltd. and/or its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
A unified tracking interface that supports logging data to different backend
"""
import dataclasses
from enum import Enum
from functools import partial
from pathlib import Path
from typing import List, Union, Dict, Any
import os
import wandb
from verl.utils.logger.aggregate_logger import LocalLogger


class Tracking(object):
    supported_backend = ['wandb', 'mlflow', 'console']

    def __init__(
        self,
        project_name: str,
        experiment_name: str,
        default_backend: Union[str, List[str]] = 'console',
        config=None
    ):
        # Normalize backend list
        if isinstance(default_backend, str):
            default_backend = [default_backend]
        for backend in default_backend:
            if backend == 'tracking':
                import warnings
                warnings.warn("`tracking` logger is deprecated. use `wandb` instead.", 
                              DeprecationWarning)
            else:
                assert backend in self.supported_backend, f'{backend} is not supported'

        self.logger = {}

        # W&B support
        if 'wandb' in default_backend or 'tracking' in default_backend:
            # Force each process to authenticate
            api_key = os.getenv("WANDB_API_KEY")
            if api_key:
                wandb.login(key=api_key, relogin=True)

            # Pick up the team namespace
            entity = os.getenv("WANDB_ENTITY")

            # Initialize the run
            wandb.init(
                entity=entity,
                project=project_name,
                name=experiment_name,
                config=config
            )
            self.logger['wandb'] = wandb

        # MLflow support (if needed)
        if 'mlflow' in default_backend:
            import mlflow
            mlflow.start_run(run_name=experiment_name)
            mlflow.log_params(_compute_mlflow_params_from_objects(config))
            from verl.utils.tracking import _MlflowLoggingAdapter
            self.logger['mlflow'] = _MlflowLoggingAdapter()

        # Console support
        if 'console' in default_backend:
            self.console_logger = LocalLogger(print_to_console=True)
            self.logger['console'] = self.console_logger

    def log(self, data, step: int, backend=None):
        for name, logger_instance in self.logger.items():
            if backend is None or name in backend:
                logger_instance.log(data=data, step=step)


class _MlflowLoggingAdapter:

    def log(self, data, step):
        import mlflow
        mlflow.log_metrics(metrics=data, step=step)


def _compute_mlflow_params_from_objects(params) -> Dict[str, Any]:
    if params is None:
        return {}

    return _flatten_dict(_transform_params_to_json_serializable(params, convert_list_to_dict=True), sep='/')


def _transform_params_to_json_serializable(x, convert_list_to_dict: bool):
    _transform = partial(_transform_params_to_json_serializable, convert_list_to_dict=convert_list_to_dict)

    if dataclasses.is_dataclass(x):
        return _transform(dataclasses.asdict(x))
    if isinstance(x, dict):
        return {k: _transform(v) for k, v in x.items()}
    if isinstance(x, list):
        if convert_list_to_dict:
            return {'list_len': len(x)} | {f'{i}': _transform(v) for i, v in enumerate(x)}
        else:
            return [_transform(v) for v in x]
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, Enum):
        return x.value

    return x


def _flatten_dict(raw: Dict[str, Any], *, sep: str) -> Dict[str, Any]:
    import pandas as pd
    ans = pd.json_normalize(raw, sep=sep).to_dict(orient='records')[0]
    assert isinstance(ans, dict)
    return ans
