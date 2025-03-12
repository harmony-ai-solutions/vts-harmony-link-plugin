# Harmony Link Plugin for VTube Studio
# (c) 2023-2025 Project Harmony.AI (contact@project-harmony.ai)
#
# Global list referencer to keep track of entities and objects
# FIXME: Turn this into proper Dependency Injection

# Object, character & user controllers
user_controlled_entity_id = None
active_entities = {}

# List of ready characters - this is used to synchronize characters finished initialization
ready_entities = []
failed_entities = []