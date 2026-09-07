ACTION_TOOLS =[{
    "type": "function",
    "name": "perform_action",
    "description": "Perform a physical avatar action: wave, walk, backflip, kiss, dropkick",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string", 
                "enum": ["wave", "walk", "backflip", "kiss", "flyingkick"]
                }
            },
        "required": ["action"],
    },
}]