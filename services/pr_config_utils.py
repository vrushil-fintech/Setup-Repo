import yaml

from app.dependencies import logger

async def parse_yaml_file(yaml_content: str):
    content = yaml.safe_load(yaml_content) or {}
    expected_keys = ["target_branches", "preferred_characteristics", "additional_instructions"]

    config_content = {}
    for key in expected_keys:
        if key in content:
            if key == "target_branches" and isinstance(content[key], list) and all(isinstance(branch, str) for branch in content[key]):
                config_content[key] = content[key]
            elif key == "preferred_characteristics" and isinstance(content[key], list) and all(isinstance(characteristic, str) for characteristic in content[key]):
                config_content[key] = [characteristic.lower() for characteristic in content[key]]
            elif key == "additional_instructions" and isinstance(content[key], list):
                config_content[key] = [inst.strip() for inst in content[key] if isinstance(inst, str) and inst.strip()]
            else:
                logger.error(f"Invalid type for key '{key}': Key Type {type(key)}, Value Type {type(content[key])}. Expected appropriate type.")

    return config_content
