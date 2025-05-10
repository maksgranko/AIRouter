from typing import Dict
from base_module import BaseModule

class ModuleRegistry:
    def __init__(self):
        self._modules: Dict[str, BaseModule] = {}

    def register(self, module: BaseModule):
        self._modules[module.get_name()] = module

    def get(self, name: str) -> BaseModule:
        return self._modules[name]

    def all(self):
        return self._modules.values()