import json
import os
from typing import Dict, List, ValuesView
from modules.base_module import BaseModule
import logging

logger = logging.getLogger(__name__)

class ModuleRegistry:
    def __init__(self, settings_file_path: str): # Добавляем settings_file_path
        self._modules: Dict[str, BaseModule] = {}
        self._module_active_status: Dict[str, bool] = {} 
        self.settings_file_path = settings_file_path
        self._load_module_statuses_from_settings()

    def _load_module_statuses_from_settings(self):
        """Загружает статусы активности модулей из settings.json."""
        try:
            if os.path.exists(self.settings_file_path):
                with open(self.settings_file_path, 'r') as f:
                    settings = json.load(f)
                    statuses = settings.get("module_statuses", {})
                    if isinstance(statuses, dict):
                        self._module_active_status = statuses
                        logger.info(f"Loaded module statuses from {self.settings_file_path}: {self._module_active_status}")
                    else:
                        logger.warning(f"Invalid format for 'module_statuses' in {self.settings_file_path}. Expected a dict.")
            else:
                logger.info(f"{self.settings_file_path} not found. Initial module statuses will be empty or default.")
                # Файл будет создан при первом сохранении настроек, если его нет
        except Exception as e:
            logger.error(f"Error loading module statuses from {self.settings_file_path}: {e}")

    def _save_module_statuses_to_settings(self):
        """Сохраняет текущие статусы активности модулей в settings.json."""
        try:
            all_settings = {}
            if os.path.exists(self.settings_file_path):
                try:
                    with open(self.settings_file_path, 'r') as f:
                        all_settings = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"Could not decode JSON from {self.settings_file_path} for saving module_statuses, will create new or overwrite.")
                    all_settings = {}
            
            all_settings["module_statuses"] = self._module_active_status
            
            os.makedirs(os.path.dirname(self.settings_file_path), exist_ok=True)
            with open(self.settings_file_path, 'w') as f:
                json.dump(all_settings, f, indent=2)
            logger.info(f"Saved module statuses to {self.settings_file_path}: {self._module_active_status}")
        except Exception as e:
            logger.error(f"Error saving module statuses to {self.settings_file_path}: {e}")

    def register(self, module: BaseModule, active_by_default: bool = True):
        """Регистрирует модуль. Статус активности берется из загруженных настроек или active_by_default."""
        module_name = module.get_name()
        self._modules[module_name] = module
        # Если статус уже был загружен из settings.json, он не перезаписывается здесь.
        # Если нет, используется active_by_default.
        if module_name not in self._module_active_status:
            self._module_active_status[module_name] = active_by_default
            logger.info(f"Module '{module_name}' registered. Initial active status (default): {active_by_default}")
            self._save_module_statuses_to_settings() # Сохраняем, если это новый модуль с дефолтным статусом
        else:
            logger.info(f"Module '{module_name}' registered. Active status from settings: {self._module_active_status[module_name]}")


    def get(self, name: str) -> BaseModule:
        """Возвращает модуль по имени, если он зарегистрирован и активен."""
        if name not in self._modules:
            raise KeyError(f"Module '{name}' not registered.")
        # Используем get_module_status, который учитывает загруженные настройки
        if not self.get_module_status(name): 
            raise KeyError(f"Module '{name}' is currently disabled.")
        return self._modules[name]

    def all_registered_modules(self) -> ValuesView[BaseModule]:
        """Возвращает все зарегистрированные модули, независимо от их статуса активности."""
        return self._modules.values()
        
    def all_active_modules(self) -> List[BaseModule]:
        """Возвращает список всех активных модулей."""
        return [mod for name, mod in self._modules.items() if self.get_module_status(name)]

    def get_module_status(self, name: str) -> bool:
        """Возвращает текущий статус активности модуля из _module_active_status."""
        return self._module_active_status.get(name, False) 

    def set_module_active(self, name: str, active: bool):
        """Устанавливает статус активности для модуля и сохраняет в settings.json."""
        if name in self._modules:
            self._module_active_status[name] = active
            logger.info(f"Module '{name}' active status set to: {active}")
            self._save_module_statuses_to_settings() # Сохраняем изменение
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

    async def reload_module_config(self, module_name: str, new_config: list):
        """
        Делегирует перезагрузку конфига модулю (например, OAIC).
        """
        if module_name not in self._modules:
            raise KeyError(f"Модуль '{module_name}' не зарегистрирован.")
        module_obj = self._modules[module_name]
        if hasattr(module_obj, "reload_module_config"):
            module_obj.reload_module_config(new_config)
        else:
            raise AttributeError(f"Модуль '{module_name}' не поддерживает reload_module_config")
