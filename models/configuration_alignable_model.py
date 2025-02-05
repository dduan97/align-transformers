from collections import OrderedDict
from typing import Any, List, Mapping, Optional

from transformers import PreTrainedTokenizer, TensorType, is_torch_available
from transformers.configuration_utils import PretrainedConfig

class AlignableLlamaConfig(PretrainedConfig):
    model_type="llama"
    def __init__(
        self,
        das_layer=15,
        das_token_range=[80, 81],
        **kwargs
    ):
        self.das_layer = das_layer
        self.das_token_range = das_token_range
        
        super().__init__(**kwargs)