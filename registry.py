from typing import Dict, List, ValuesView
from base_module import BaseModule
import logging

logger = logging.getLogger(__name__)

class ModuleRegistry:
    def __init__(self):
        self._modules: Dict[str, BaseModule] = {}
        self._module_active_status: Dict[str, bool] = {} # Статус активности модуля

    def register(self, module: BaseModule, active_by_default: bool = True):
        """Регистрирует модуль и устанавливает его начальный статус активности."""
        module_name = module.get_name()
        self._modules[module_name] = module
        self._module_active_status[module_name] = active_by_default
        logger.info(f"Module '{module_name}' registered. Initial active status: {active_by_default}")

    def get(self, name: str) -> BaseModule:
        """Возвращает модуль по имени, если он зарегистрирован и активен."""
        if name not in self._modules:
            raise KeyError(f"Module '{name}' not registered.")
        if not self._module_active_status.get(name, False):
            # Вместо KeyError можно возвращать специальную ошибку или None,
            # но для совместимости с текущей логикой get_module в main.py, KeyError предпочтительнее.
            raise KeyError(f"Module '{name}' is currently disabled.")
        return self._modules[name]

    def all_registered_modules(self) -> ValuesView[BaseModule]:
        """Возвращает все зарегистрированные модули, независимо от их статуса активности."""
        return self._modules.values()
        
    def all_active_modules(self) -> List[BaseModule]:
        """Возвращает список всех активных модулей."""
        return [mod for name, mod in self._modules.items() if self._module_active_status.get(name, False)]

    def get_module_status(self, name: str) -> bool:
        """Возвращает текущий статус активности модуля."""
        return self._module_active_status.get(name, False) # False, если модуль не найден

    def set_module_active(self, name: str, active: bool):
        """Устанавливает статус активности для модуля."""
        if name in self._modules:
            self._module_active_status[name] = active
            logger.info(f"Module '{name}' active status set to: {active}")
        else:
            logger.warning(f"Attempted to set active status for unregistered module '{name}'.")
            
    def get_all_module_statuses(self) -> Dict[str, bool]:
        """Возвращает словарь со статусами всех зарегистрированных модулей."""
        return self._module_active_status.copy()

    # Старый метод all() теперь заменен на all_active_modules() или all_registered_modules()
    # Для обратной совместимости, если где-то используется all() и ожидаются только активные:
    def all(self) -> List[BaseModule]:
        logger.warning("ModuleRegistry.all() is deprecated. Use all_active_modules() or all_registered_modules(). Falling back to all_active_modules().")
        return self.all_active_modules()
