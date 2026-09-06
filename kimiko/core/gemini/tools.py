ACTION_TOOLS =[{
    "type": "function",
    "name": "perform_action",
    "description": "Thực hiện 1 hành động vật lý: wave, walk, backflip, kiss, dropkick",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string", 
                "enum": ["wave", "walk", "backflip", "kiss", "dropkick"]
                }
            },
        "required": ["action"],
    },
}]