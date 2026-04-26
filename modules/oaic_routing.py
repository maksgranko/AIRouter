from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException


def parse_instance_and_model_id(model_identifier: str) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(model_identifier, str):
        return None, None
    if model_identifier.startswith("OAIC/"):
        parts = model_identifier.split("/", 2)
        if len(parts) < 3:
            return None, None
        return parts[1], parts[2]
    if model_identifier.startswith("openai_") and "/" in model_identifier:
        instance_and_rest = model_identifier[len("openai_"):]
        parts = instance_and_rest.split("/", 1)
        if len(parts) < 2:
            return None, None
        instance = parts[0]
        provider_model_path = parts[1]
        if not instance or not provider_model_path:
            return None, None
        return instance, provider_model_path
    return None, None


def get_instance_config(
    instances_config: Sequence[Dict[str, Any]],
    instance_name: str,
    include_disabled: bool = False,
) -> Optional[Dict[str, Any]]:
    for conf in instances_config:
        if conf.get("name") != instance_name:
            continue
        if include_disabled or conf.get("enabled", True):
            return conf
    return None


def parse_target_reference(reference: Any, default_instance: str) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(reference, str) or not reference.strip():
        return None, None
    normalized = reference.strip()
    parsed_instance, parsed_model = parse_instance_and_model_id(normalized)
    if parsed_instance and parsed_model:
        return parsed_instance, parsed_model
    if "/" in normalized:
        parts = normalized.split("/", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
        return None, None
    return default_instance, normalized


def resolve_model_targets(
    instances_config: Sequence[Dict[str, Any]],
    instance_name: str,
    model_name: str,
    path: Optional[List[Tuple[str, str]]] = None,
    depth: int = 0,
    max_depth: int = 16,
) -> List[Tuple[str, str]]:
    if path is None:
        path = []
    node = (instance_name, model_name)
    if depth > max_depth:
        raise HTTPException(
            status_code=400,
            detail=f"Too many alias/redirect hops while resolving model '{instance_name}/{model_name}'.",
        )
    if node in path:
        raise HTTPException(
            status_code=400,
            detail=f"Model alias/redirect cycle detected near '{instance_name}/{model_name}'.",
        )

    instance_conf = get_instance_config(instances_config, instance_name, include_disabled=True)
    if not instance_conf:
        raise HTTPException(status_code=400, detail=f"Instance '{instance_name}' not found.")

    redirects = instance_conf.get("model_redirects")
    aliases = instance_conf.get("model_aliases")
    if not isinstance(redirects, dict):
        redirects = {}
    if not isinstance(aliases, dict):
        aliases = {}

    mapping_value = None
    if model_name in redirects:
        mapping_value = redirects[model_name]
    elif model_name in aliases:
        mapping_value = aliases[model_name]

    if mapping_value is None:
        return [node]

    if isinstance(mapping_value, str):
        next_instance, next_model = parse_target_reference(mapping_value, instance_name)
        if not next_instance or not next_model:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model mapping for '{instance_name}/{model_name}'.",
            )
        return resolve_model_targets(
            instances_config,
            next_instance,
            next_model,
            path=path + [node],
            depth=depth + 1,
            max_depth=max_depth,
        )

    if isinstance(mapping_value, list):
        resolved: List[Tuple[str, str]] = []
        for ref in mapping_value:
            next_instance, next_model = parse_target_reference(ref, instance_name)
            if not next_instance or not next_model:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid model mapping list for '{instance_name}/{model_name}'.",
                )
            nested = resolve_model_targets(
                instances_config,
                next_instance,
                next_model,
                path=path + [node],
                depth=depth + 1,
                max_depth=max_depth,
            )
            for item in nested:
                if item not in resolved:
                    resolved.append(item)
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid empty model mapping list for '{instance_name}/{model_name}'.",
            )
        return resolved

    raise HTTPException(
        status_code=400,
        detail=f"Invalid model mapping type for '{instance_name}/{model_name}'.",
    )


def build_failsafe_chain(instances_config: Sequence[Dict[str, Any]], primary_instance: str) -> List[str]:
    instance_conf = get_instance_config(instances_config, primary_instance, include_disabled=False)
    chain = [primary_instance]
    if instance_conf and instance_conf.get("failsafe_providers"):
        for prov in instance_conf["failsafe_providers"]:
            if prov not in chain:
                chain.append(prov)
        return chain

    enabled_instances = [inst["name"] for inst in instances_config if inst.get("enabled", True)]
    if primary_instance in enabled_instances:
        enabled_instances = [n for n in enabled_instances if n != primary_instance]
    enabled_instances.insert(0, primary_instance)
    return enabled_instances
