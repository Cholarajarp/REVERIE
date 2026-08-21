import { CharacterState, Whisper, SceneRecord, WorldState } from "../store/simulationStore";

export const INITIAL_WORLD_STATE: WorldState = {
  current_time: new Date().toISOString(),
  weather: "Sunny",
};

export const INITIAL_CHARACTERS: CharacterState[] = [
  {
    name: "Maya",
    current_location: "The Mill",
    current_goal: "Serve coffee to customers and find time to write a new poem.",
    mood: "Warm but guarded",
  },
  {
    name: "Leo",
    current_location: "Park",
    current_goal: "Write at least 500 words of my novel without getting distracted.",
    mood: "Anxious and proud",
  },
  {
    name: "Zara",
    current_location: "Restaurant",
    current_goal: "Create a new special dish for the dinner rush.",
    mood: "Fiercely driven",
  },
  {
    name: "Nora",
    current_location: "Street",
    current_goal: "Settle back into town without running into Maya immediately.",
    mood: "Anxious and regretful",
  },
];

export const INITIAL_WHISPERS: Whisper[] = [
  {
    id: "seed-whisper-1",
    user: "Maya",
    text: "Another quiet morning at The Mill. I wonder if Leo will come by today...",
    ts: new Date().toISOString(),
  },
  {
    id: "seed-whisper-2",
    user: "Leo",
    text: "The park is perfect for writing. Nobody will bother me here.",
    ts: new Date().toISOString(),
  },
];

export const SAMPLE_CINEMA_SCENE: SceneRecord = {
  scene_id: "SCENE_DEMO_001",
  characters_involved: ["Maya", "Nora"],
  drama_score: 0.88,
  veo_prompt: "Cinematic close-up of two women meeting unexpectedly at a small-town coffee shop. Warm golden lighting, shallow depth of field, emotional tension, 2.39:1 anamorphic framing.",
  video_uri: "",
  status: "rendering",
};
