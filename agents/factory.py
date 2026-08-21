from typing import Dict, Any, List
from models.schema import CharacterState
from agents.character_agent import CharacterAgent

def create_character(config: Dict[str, Any]) -> CharacterAgent:
    """
    Creates a dynamic character agent from a configuration dictionary.

    Expected config format:
    {
        "name": "Peter Parker",
        "current_location": "Street",
        "current_goal": "Patrol the neon city.",
        "mood": "Determined",
        "memory_stream": ["I am Spider-Man.", "I need money for rent."],
        "personality_description": "You are Spider-Man in 2050...",
        "visual_description": "Young man, late 20s, brown hair, red-and-blue suit, athletic build",
        "voice_id": "en-US-Studio-O"
    }
    """
    state = CharacterState(
        name=config.get("name", "Unknown Character"),
        current_location=config.get("current_location", "Unknown Location"),
        current_goal=config.get("current_goal", "Exist."),
        mood=config.get("mood", "Neutral"),
        memory_stream=config.get("memory_stream", ["I have no memories."]),
        visual_description=config.get("visual_description", ""),
    )

    personality = config.get(
        "personality_description",
        f"You are {state.name}. Your goal is {state.current_goal}."
    )

    agent = CharacterAgent(character_state=state, personality_description=personality)
    # voice_id lives on the agent (not in CharacterState) so the simulation loop
    # can read it for TTS synthesis without changing the world-state schema.
    agent.voice_id = config.get("voice_id", "en-US-Studio-O")
    return agent

def create_dynamic_characters(character_configs: List[Dict[str, Any]]) -> List[CharacterAgent]:
    """Factory function to instantiate dynamic characters from a list of configs."""
    return [create_character(config) for config in character_configs]
