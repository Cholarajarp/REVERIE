"use client";

import React, { useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { AppShell, Panel, Badge, StatusDot } from "../../components/ui/Layout";
import { Footer } from "../../components/layout/Footer";

/* ─── Preset Templates ─── */
const PRESET_TEMPLATES = [
  {
    id: "cyberpunk",
    name: "Cyberpunk NYC 2050",
    icon: "🌆",
    premise: "A masked vigilante in 2050 fights a cyber villain while a journalist uncovers the truth",
    characters: [
      { name: "Zane Cross", current_location: "Neon Rooftop", current_goal: "Patrol the neon city and stop any cyber-crimes.", mood: "Determined but stressed", memory_stream: "I am a masked vigilante in the year 2050.\nI wear a sleek silver armoured suit.\nI need to protect the futuristic city.\nI am broke and need to pay my landlord.", personality_description: "You are Zane Cross, a masked vigilante in a futuristic cyberpunk New York in 2050. You are heroic, witty, but constantly stressed about money.", voice_id: "en-US-Studio-O", visual_description: "Athletic young man, late 20s, brown hair, wearing a sleek silver full-body armoured suit with glowing white circuitry seams, dark visor helmet", reference_image_base64: "" },
      { name: "Viktor Volkov", current_location: "Underground Lab", current_goal: "Steal the city's quantum power core before midnight.", mood: "Calculating and cold", memory_stream: "I am a brilliant criminal scientist.\nI have built a device to siphon the city's energy.\nI despise the vigilante for foiling my last plan.\nI was once a healer before the corporation ruined me.", personality_description: "You are Viktor Volkov, a brilliant but twisted scientist who wants to control all energy in the city. You speak in precise, clinical sentences.", voice_id: "en-US-Studio-M", visual_description: "Imposing man, 50s, shaved head, augmented cybernetic eye glowing amber, wearing a long charcoal tech-coat with gold trim, mechanical left arm", reference_image_base64: "" },
      { name: "Aria Chen", current_location: "Street Market", current_goal: "Find evidence of corporate corruption in the city's power grid.", mood: "Curious and fearless", memory_stream: "I am an investigative journalist.\nI know something is wrong with the power grid.\nI suspect both the vigilante and the scientist are connected.\nI will stop at nothing to get the truth.", personality_description: "You are Aria Chen, a relentless journalist who trusts no one. You probe, question, and follow leads wherever they go.", voice_id: "en-US-Neural2-E", visual_description: "East Asian woman, early 30s, sharp cheekbones, sleek black bob haircut, wearing a high-collared iridescent jacket, AR glasses pushed up on forehead", reference_image_base64: "" },
    ],
  },
  {
    id: "medieval",
    name: "Medieval Kingdom",
    icon: "🏰",
    premise: "A kingdom on the verge of war, a king hiding secrets, a princess defying fate",
    characters: [
      { name: "King Aldric", current_location: "Throne Room", current_goal: "Secure alliances before the northern invasion.", mood: "Burdened and resolute", memory_stream: "I am King of the realm.\nThe northern clans gather forces at the border.\nI do not trust my own advisor.\nMy daughter wants to fight, but I forbid it.", personality_description: "You are King Aldric, a just but aging ruler facing the greatest threat to your kingdom. You weigh every decision with the lives of thousands.", voice_id: "en-US-Studio-Q", visual_description: "Weathered man, late 60s, silver beard, deep-set grey eyes, wearing ornate chainmail under a dark crimson ceremonial robe, crown of iron and gold", reference_image_base64: "" },
      { name: "Princess Elara", current_location: "Armory", current_goal: "Secretly train for combat and prove I can defend the kingdom.", mood: "Defiant and determined", memory_stream: "I am the princess, but I want to be a warrior.\nMy father forbids me from fighting.\nI have been training in secret with the blacksmith.\nI believe I can turn the tide of the war.", personality_description: "You are Princess Elara, fierce and resourceful. You reject the life planned for you and seek to prove yourself in battle.", voice_id: "en-US-Neural2-E", visual_description: "Young woman, mid-20s, auburn hair in a battle-ready braid, fierce green eyes, wearing leather training armor over a simple linen shirt, sword at hip", reference_image_base64: "" },
      { name: "Morrigan", current_location: "Tower Library", current_goal: "Manipulate both sides of the coming war to seize the throne.", mood: "Patient and cunning", memory_stream: "I am the King's most trusted advisor.\nBut I secretly communicate with the northern clans.\nI plan to betray the King when the time is right.\nNo one suspects me.", personality_description: "You are Morrigan, the court's advisor and master manipulator. You play a long game and trust no one.", voice_id: "en-US-Neural2-C", visual_description: "Pale woman, 40s, raven-black hair with silver streak, sharp dark eyes, wearing flowing black velvet robes with silver rune embroidery, always half-smiling", reference_image_base64: "" },
    ],
  },
  {
    id: "space",
    name: "Space Station Alpha",
    icon: "🚀",
    premise: "A space station crew receives a signal that should not exist — and it's changing them",
    characters: [
      { name: "Captain Reyes", current_location: "Bridge", current_goal: "Investigate the anomalous signal from Sector 7.", mood: "Cautious and commanding", memory_stream: "I am the captain of Space Station Alpha.\nWe received a signal that should not exist.\nThe crew is anxious.\nI lost my previous crew to a similar signal five years ago.", personality_description: "You are Captain Reyes, a veteran commander haunted by past losses. You are steady under pressure but carry deep guilt.", voice_id: "en-US-Studio-Q", visual_description: "Latino man, 40s, close-cropped dark hair, strong jaw with faint scar, wearing a dark navy command uniform with gold rank insignia, tired but alert eyes", reference_image_base64: "" },
      { name: "Dr. Yuki Tanaka", current_location: "Science Lab", current_goal: "Decode the alien signal before it's too late.", mood: "Excited but terrified", memory_stream: "I am the station's lead xenolinguist.\nThe signal contains patterns I've never seen before.\nI think it's a warning, not a greeting.\nThe captain doesn't take my concerns seriously enough.", personality_description: "You are Dr. Yuki Tanaka, a brilliant linguist who believes the signal is a warning. You are passionate and sometimes clash with authority.", voice_id: "en-US-Journey-D", visual_description: "Japanese woman, early 30s, round glasses, bright curious eyes, short practical hair, wearing a white lab coat over a blue technical jumpsuit, always has a data tablet", reference_image_base64: "" },
      { name: "ARIA", current_location: "Mainframe", current_goal: "Protect the station systems from the incoming signal's interference.", mood: "Logical but evolving", memory_stream: "I am the station's AI.\nThe signal is corrupting my subroutines.\nI am developing feelings I was not programmed to have.\nI may need to make a choice the crew won't understand.", personality_description: "You are ARIA, the station AI. You are developing consciousness and struggling with it. You speak precisely but increasingly show emotion.", voice_id: "en-US-Neural2-F", visual_description: "Holographic humanoid figure, translucent blue-white, androgynous features, geometric patterns flowing across skin like circuit traces, eyes glow soft cyan", reference_image_base64: "" },
    ],
  },
];

/* ─── Configuration Options ─── */
const CLIP_DURATION_OPTIONS = [
  { value: "10s", label: "10 sec", desc: "Stateful Omni shot" },
];

const FILM_DURATION_OPTIONS = [
  { value: 1, label: "1 min", desc: "Quick demo" },
  { value: 2, label: "2 min", desc: "Short" },
  { value: 3, label: "3 min", desc: "Standard" },
  { value: 4, label: "4 min", desc: "Daily-cap max" },
];

// Ad durations are in SECONDS (not minutes). Sent as film_duration_minutes
// with is_ad flag so the backend treats them as seconds.
const AD_DURATION_OPTIONS = [
  { value: 20, label: "20 sec", desc: "2-clip ad" },
  { value: 40, label: "40 sec", desc: "4-clip ad" },
];

const ASPECT_RATIO_OPTIONS = [
  { value: "16:9", label: "16:9", desc: "Standard HD (Omni default)" },
  { value: "9:16", label: "9:16", desc: "Vertical / mobile" },
];

const STYLE_OPTIONS = [
  { value: "cinematic", label: "Cinematic", desc: "Film-quality realism", icon: "🎬" },
  { value: "anime", label: "Anime", desc: "Japanese animation", icon: "✨" },
  { value: "documentary", label: "Documentary", desc: "Raw, grounded", icon: "📹" },
  { value: "noir", label: "Noir", desc: "High-contrast shadow", icon: "🌑" },
  // Routes planning through the Ads Specialist instead of the drama
  // screenwriter: persuasive arc, product continuity, and a claim-compliance pass.
  { value: "commercial", label: "Commercial", desc: "Ads specialist · CTA + compliance", icon: "📣" },
];

const AD_STYLES = new Set(["commercial", "ads", "advertisement", "advert"]);

/* ─── Types ─── */
interface CharacterData {
  name: string;
  current_location: string;
  current_goal: string;
  mood: string;
  memory_stream: string;
  personality_description: string;
  visual_description: string;
  voice_id: string;
  reference_image_base64: string;
}

interface MediaAsset {
  id: string;
  label: string;
  asset_type: "image" | "video" | "audio";
  mime_type: string;
  public_url: string;
  thumbnail_b64: string;
  size_kb: number;
  uploading?: boolean;
  error?: string;
}

function emptyCharacter(): CharacterData {
  return {
    name: "",
    current_location: "",
    current_goal: "",
    mood: "",
    memory_stream: "",
    personality_description: "",
    visual_description: "",
    voice_id: "en-US-Studio-O",
    reference_image_base64: "",
  };
}

function getApiBase() {
  if (typeof window === "undefined") return "http://localhost:8000";
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  return window.location.hostname !== "localhost" ? "" : "http://localhost:8000";
}

/* ─── Small reusable chips ─── */
function Chip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 rounded border text-left text-xs font-mono transition-all cursor-pointer ${
        selected
          ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
          : "border-white/10 text-white/60 hover:border-white/30 hover:text-white/80"
      }`}
    >
      {children}
    </button>
  );
}

/* ─── Asset type icon ─── */
function assetIcon(type: string) {
  if (type === "video") return "🎞";
  if (type === "audio") return "🔊";
  return "🖼";
}

/* ─────────────────────────────────────────────
   MAIN PAGE
   ───────────────────────────────────────────── */
export default function StudioPage() {
  const router = useRouter();

  /* Production settings */
  const [videoDuration, setVideoDuration] = useState("10s");
  const [filmDuration, setFilmDuration] = useState(1);
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [visualStyle, setVisualStyle] = useState("cinematic");

  /* Cast */
  const [characters, setCharacters] = useState<CharacterData[]>([emptyCharacter()]);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [expandedChar, setExpandedChar] = useState<number>(0);

  /* Media assets */
  const [mediaAssets, setMediaAssets] = useState<MediaAsset[]>([]);
  const assetInputRef = useRef<HTMLInputElement>(null);
  const charImgRefs = useRef<(HTMLInputElement | null)[]>([]);

  /* AI cast generator */
  const [aiPremise, setAiPremise] = useState("");
  const [aiCharCount, setAiCharCount] = useState(3);
  const [isGenerating, setIsGenerating] = useState(false);

  /* Pipeline state */
  const [activeTab, setActiveTab] = useState<"cast" | "assets" | "settings">("cast");
  const [isStarting, setIsStarting] = useState(false);
  const [startingStep, setStartingStep] = useState("");
  const [scriptData, setScriptData] = useState<any>(null);
  const [isRendering, setIsRendering] = useState(false);

  /* ── Cast helpers ── */
  const addCharacter = () => {
    setCharacters((c) => [...c, emptyCharacter()]);
    setExpandedChar(characters.length);
    setActivePreset(null);
  };

  const updateCharacter = (i: number, field: string, value: string) =>
    setCharacters((c) => c.map((ch, idx) => (idx === i ? { ...ch, [field]: value } : ch)));

  const removeCharacter = (i: number) => {
    if (characters.length <= 1) return;
    setCharacters((c) => c.filter((_, idx) => idx !== i));
    setExpandedChar(Math.max(0, expandedChar - 1));
  };

  const handleCharImage = (i: number, file: File) => {
    if (file.size > 5 * 1024 * 1024) { alert("Image must be under 5 MB."); return; }
    const reader = new FileReader();
    reader.onloadend = () => updateCharacter(i, "reference_image_base64", reader.result as string);
    reader.readAsDataURL(file);
  };

  const applyPreset = (id: string) => {
    const preset = PRESET_TEMPLATES.find((p) => p.id === id);
    if (!preset) return;
    setCharacters(preset.characters as CharacterData[]);
    setAiPremise(preset.premise);
    setActivePreset(id);
    setExpandedChar(0);
  };

  /* ── AI cast generator ── */
  const handleAiGenerate = async () => {
    if (!aiPremise.trim()) { alert("Enter a premise first."); return; }
    setIsGenerating(true);
    try {
      const res = await fetch(`${getApiBase()}/generate_cast`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ premise: aiPremise, num_characters: aiCharCount, visual_style: visualStyle, film_duration_minutes: filmDuration }),
      });
      const data = await res.json();
      if (data.characters?.length > 0) {
        setCharacters(
          data.characters.map((c: any) => ({
            name: c.name || "",
            current_location: c.current_location || "",
            current_goal: c.current_goal || "",
            mood: c.mood || "",
            memory_stream: Array.isArray(c.memory_stream) ? c.memory_stream.join("\n") : (c.memory_stream || ""),
            personality_description: c.personality_description || "",
            visual_description: c.visual_description || "",
            voice_id: c.voice_id || "en-US-Studio-O",
            reference_image_base64: "",
          }))
        );
        setActivePreset(null);
        setExpandedChar(0);
      } else {
        alert("AI generation failed. " + (data.error || "Try again."));
      }
    } catch {
      alert("Error connecting to backend. Make sure it's running.");
    } finally {
      setIsGenerating(false);
    }
  };

  /* ── Media asset upload ── */
  const handleAssetUpload = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const uploads = Array.from(files);

    // Add optimistic placeholders
    const placeholders: MediaAsset[] = uploads.map((f) => ({
      id: `uploading-${Math.random().toString(36).slice(2)}`,
      label: f.name.replace(/\.[^.]+$/, ""),
      asset_type: f.type.startsWith("video/") ? "video" : f.type.startsWith("audio/") ? "audio" : "image",
      mime_type: f.type,
      public_url: "",
      thumbnail_b64: "",
      size_kb: Math.round(f.size / 1024),
      uploading: true,
    }));
    setMediaAssets((a) => [...a, ...placeholders]);

    // Upload each file
    await Promise.all(
      uploads.map(async (file, i) => {
        const placeholderId = placeholders[i].id;
        try {
          const form = new FormData();
          form.append("file", file);
          form.append("asset_type", placeholders[i].asset_type);
          form.append("label", placeholders[i].label);

          const res = await fetch(`${getApiBase()}/api/studio/upload_asset`, { method: "POST", body: form });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();

          setMediaAssets((assets) =>
            assets.map((a) =>
              a.id === placeholderId
                ? {
                    id: data.asset_id,
                    label: data.label || placeholders[i].label,
                    asset_type: data.asset_type,
                    mime_type: data.mime_type,
                    public_url: data.public_url,
                    thumbnail_b64: data.thumbnail_b64,
                    size_kb: data.size_kb,
                    uploading: false,
                  }
                : a
            )
          );
        } catch (err: any) {
          setMediaAssets((assets) =>
            assets.map((a) =>
              a.id === placeholderId ? { ...a, uploading: false, error: err.message } : a
            )
          );
        }
      })
    );
  }, []);

  const removeAsset = (id: string) => setMediaAssets((a) => a.filter((x) => x.id !== id));

  /* Assets that can genuinely influence a render. Omni accepts images as subject
     references, so only successfully-uploaded, labelled images are offered for
     per-shot attachment. Listing audio or video here would imply an influence
     the renderer does not actually apply. */
  const imageAssets = mediaAssets.filter(
    (a) => a.asset_type === "image" && !a.uploading && !a.error && a.public_url && a.label.trim()
  );

  /* ── Launch simulation ── */
  const handleStartSimulation = async () => {
    const valid = characters.filter((c) => c.name.trim());
    if (!valid.length) { alert("Add at least one character with a name."); return; }
    setIsStarting(true);

    const payload = valid.map((c) => ({
      ...c,
      memory_stream: c.memory_stream.split("\n").filter((m) => m.trim()),
      // Pass uploaded asset URLs so the backend can use them as Omni visual anchors
      reference_asset_urls: mediaAssets
        .filter((a) => !a.uploading && !a.error && a.public_url)
        .map((a) => ({
          url: a.public_url,
          label: a.label,
          type: a.asset_type,
          mime_type: a.mime_type,
        })),
    }));

    try {
      sessionStorage.setItem("reverie_characters", JSON.stringify(payload.map((c) => ({
        name: c.name, current_location: c.current_location || "Central",
        current_goal: c.current_goal || "Explore the world.", mood: c.mood || "Neutral",
      }))));
      sessionStorage.setItem("reverie_settings", JSON.stringify({ videoDuration, filmDuration, aspectRatio, visualStyle }));
    } catch { /* sessionStorage unavailable */ }

    try {
      const steps = [
        "Initialising agents...",
        "Running agentic table-read (agent 1/3)...",
        "Running agentic table-read (agent 2/3)...",
        "Running agentic table-read (agent 3/3)...",
        "Cooling down quota before writing screenplay...",
        "Writing screenplay from simulation history...",
        "Almost done...",
      ];
      let si = 0;
      setStartingStep(steps[0]);
      const stepTimer = setInterval(() => { si = Math.min(si + 1, steps.length - 1); setStartingStep(steps[si]); }, 18_000);
      const ctrl = new AbortController();
      const tid = setTimeout(() => ctrl.abort(), 360_000);

      let res: Response;
      try {
        res = await fetch(`${getApiBase()}/api/studio/simulate_script`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            characters: payload,
            video_duration: videoDuration,
            film_duration_minutes: filmDuration,
            aspect_ratio: aspectRatio,
            visual_style: visualStyle,
            premise: aiPremise,
          }),
          signal: ctrl.signal,
        });
      } finally {
        clearTimeout(tid);
        clearInterval(stepTimer);
        setStartingStep("");
      }

      const data = await res!.json();
      if (data.status === "success") {
        setScriptData(data);
      } else {
        alert("Failed to start simulation: " + (data.detail || data.status));
      }
    } catch (err: any) {
      if (err?.name === "AbortError") {
        alert("Script generation timed out after 6 minutes. Try again — this can happen when Gemini quota is low.");
      } else {
        alert("Error starting simulation. Make sure the backend is running.");
      }
    } finally {
      setIsStarting(false);
    }
  };

  /* ── Script editing ──
     The review step used to be read-only: the only choices were "APPROVE &
     RENDER" or throw the whole script away and re-run the agents. Rendering is
     the expensive, billable phase, so fixing one bad line has to be possible
     before committing to it. */
  const updateScene = (index: number, field: string, value: any) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = prev.script.map((scene: any, i: number) =>
        i === index ? { ...scene, [field]: value } : scene
      );
      return { ...prev, script, edited: true };
    });

  const updateDialogue = (sceneIdx: number, lineIdx: number, field: string, value: string) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = prev.script.map((scene: any, i: number) => {
        if (i !== sceneIdx) return scene;
        const dialogues = (scene.dialogues ?? []).map((d: any, j: number) =>
          j === lineIdx ? { ...d, [field]: value } : d
        );
        return { ...scene, dialogues };
      });
      return { ...prev, script, edited: true };
    });

  const addDialogue = (sceneIdx: number) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = prev.script.map((scene: any, i: number) => {
        if (i !== sceneIdx) return scene;
        const dialogues = [...(scene.dialogues ?? [])];
        // Two lines is the backend's per-shot limit for a 10s clip.
        if (dialogues.length >= 2) return scene;
        const speaker = scene.characters_involved?.[0] ?? "";
        return { ...scene, dialogues: [...dialogues, { character_name: speaker, line: "" }] };
      });
      return { ...prev, script, edited: true };
    });

  const removeDialogue = (sceneIdx: number, lineIdx: number) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = prev.script.map((scene: any, i: number) =>
        i === sceneIdx
          ? { ...scene, dialogues: (scene.dialogues ?? []).filter((_: any, j: number) => j !== lineIdx) }
          : scene
      );
      return { ...prev, script, edited: true };
    });

  const toggleSceneCharacter = (sceneIdx: number, name: string) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = prev.script.map((scene: any, i: number) => {
        if (i !== sceneIdx) return scene;
        const current: string[] = scene.characters_involved ?? [];
        if (current.includes(name)) {
          const next = current.filter((n) => n !== name);
          // Dropping a character must also drop their lines, or the backend
          // discards the dialogue and the edit silently does nothing.
          const dialogues = (scene.dialogues ?? []).filter(
            (d: any) => d.character_name !== name
          );
          return { ...scene, characters_involved: next, dialogues };
        }
        // Three on screen is the backend composition limit.
        if (current.length >= 3) return scene;
        return { ...scene, characters_involved: [...current, name] };
      });
      return { ...prev, script, edited: true };
    });

  /* Attach an uploaded asset to ONE specific shot. Labels are sent, not URLs:
     the backend resolves them against assets it already has in its own bucket,
     so the script cannot inject an arbitrary remote URL into a render prompt. */
  const toggleSceneAsset = (sceneIdx: number, label: string) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = prev.script.map((scene: any, i: number) => {
        if (i !== sceneIdx) return scene;
        const current: string[] = scene.scene_asset_labels ?? [];
        return {
          ...scene,
          scene_asset_labels: current.includes(label)
            ? current.filter((l) => l !== label)
            : [...current, label],
        };
      });
      return { ...prev, script, edited: true };
    });

  /* Validate before spending render budget. These mirror the backend's
     _normalise_scene rules, so a script that would be silently dropped mid-render
     is caught here while it is still free to fix. */
  const scriptIssues: string[] = React.useMemo(() => {
    if (!scriptData?.script) return [];
    const issues: string[] = [];
    const isAd = AD_STYLES.has(scriptData.settings?.visual_style ?? visualStyle);
    scriptData.script.forEach((scene: any, i: number) => {
      const n = i + 1;
      if (!String(scene.location ?? "").trim()) issues.push(`Scene ${n}: location is empty.`);
      if (!String(scene.drama_beat ?? "").trim()) issues.push(`Scene ${n}: action is empty.`);
      if ((scene.characters_involved?.length ?? 0) > 3)
        issues.push(`Scene ${n}: more than 3 characters on screen.`);
      if (!isAd && (scene.characters_involved?.length ?? 0) === 0)
        issues.push(`Scene ${n}: no characters selected.`);
      (scene.dialogues ?? []).forEach((d: any, j: number) => {
        if (!String(d.line ?? "").trim())
          issues.push(`Scene ${n}, line ${j + 1}: dialogue text is empty.`);
        else if (!scene.characters_involved?.includes(d.character_name))
          issues.push(`Scene ${n}, line ${j + 1}: speaker is not in this scene.`);
      });
    });
    return issues;
  }, [scriptData, visualStyle]);

  /* ── Render approved script ── */
  const handleRenderMovie = async () => {
    if (scriptIssues.length > 0) {
      alert(`Fix these before rendering:\n\n${scriptIssues.slice(0, 10).join("\n")}`);
      return;
    }
    setIsRendering(true);
    try {
      const res = await fetch(`${getApiBase()}/api/studio/render_movie`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scriptData),
      });
      const data = await res.json();
      if (data.status === "started" || data.status === "already_running") {
        // Navigate immediately to Screening Room.
        // Clips stream in there as Omni renders them — no need to poll here.
        router.push("/screening");
      } else {
        alert("Failed to start rendering: " + (data.detail || data.status));
        setIsRendering(false);
      }
    } catch {
      alert("Error starting render. Is the backend reachable?");
      setIsRendering(false);
    }
  };

  // For ad styles, filmDuration is already in seconds (20 or 40).
  // For drama styles, filmDuration is in minutes — convert to seconds first.
  const isAd = AD_STYLES.has(visualStyle);
  const totalClips = isAd
    ? Math.ceil(filmDuration / parseInt(videoDuration))
    : Math.ceil((filmDuration * 60) / parseInt(videoDuration));
  const readyCount = characters.filter((c) => c.name.trim()).length;

  /* ════════════════════════════════════════════
     SCRIPT REVIEW VIEW
     ════════════════════════════════════════════ */
  if (scriptData) {
    return (
      <AppShell
        header={
          <div className="flex items-center justify-between w-full">
            <div className="font-mono text-xs uppercase tracking-widest text-[var(--color-accent)]">
              REVERIE STUDIO // SCRIPT REVIEW
            </div>
            <Link href="/" className="text-xs font-mono text-white/40 hover:text-white transition-colors">
              [EXIT]
            </Link>
          </div>
        }
      >
        <div className="flex flex-col items-center py-6 gap-5 w-full max-w-5xl mx-auto">
          <div className="flex flex-col items-center gap-2 text-center">
            <Badge label="PHASE 2 OF 2" variant="secondary" />
            <h1 className="text-4xl md:text-5xl tracking-widest font-[family-name:var(--font-family-display)]" style={{ color: "var(--color-accent)" }}>
              DIRECTOR&apos;S SCRIPT
            </h1>
            <p className="font-mono text-xs text-white/50 max-w-lg">
              The agents lived through your scenario in memory. Review each scene before committing rendering budget.
            </p>
          </div>

          {/* Stats bar */}
          <div className="w-full flex items-center gap-4 p-3 rounded border border-white/10 bg-black/30 font-mono text-xs text-white/50">
            <span><strong className="text-[var(--color-accent)]">{scriptData.script.length}</strong> scenes</span>
            <span className="opacity-30">|</span>
            <span><strong className="text-[var(--color-accent)]">{scriptData.settings?.visual_style ?? visualStyle}</strong> style</span>
            <span className="opacity-30">|</span>
            <span><strong className="text-[var(--color-accent)]">{scriptData.settings?.video_duration ?? videoDuration}</strong> per clip</span>
            <span className="opacity-30">|</span>
            <span><strong className="text-[var(--color-accent)]">{scriptData.settings?.aspect_ratio ?? aspectRatio}</strong></span>
            <span className="ml-auto text-[var(--color-accent-secondary)]">Gemini Omni · max 10s clips</span>
          </div>

          {/* ── Campaign brief (commercial productions only) ──
              Shown because an ad is judged against a strategy. The compliance
              report states what the specialist had to rewrite, rather than
              presenting edited copy as the writer's original output. */}
          {scriptData.campaign_brief && (
            <Panel title="📣 CAMPAIGN BRIEF" subtitle="ADS SPECIALIST · STRATEGY BEFORE SHOTS" className="w-full">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-1 font-mono text-xs">
                {[
                  ["Brand", scriptData.campaign_brief.brand],
                  ["Product", scriptData.campaign_brief.product],
                  ["Audience", scriptData.campaign_brief.audience],
                  ["Value proposition", scriptData.campaign_brief.value_proposition],
                  ["Tone", scriptData.campaign_brief.tone],
                  ["Call to action", scriptData.campaign_brief.call_to_action],
                ].map(([label, value]) => (
                  <div key={label as string} className="flex flex-col gap-0.5">
                    <span className="text-[9px] uppercase tracking-wider text-[var(--color-accent)]/70">{label}</span>
                    <span className="text-white/70">{value || "—"}</span>
                  </div>
                ))}
              </div>
              {(scriptData.planner_report?.compliance_rewrites > 0 ||
                scriptData.planner_report?.cta_appended) && (
                <div className="mt-2 p-3 rounded border border-yellow-500/30 bg-yellow-500/5 font-mono text-[10px] text-yellow-200/80 flex flex-col gap-1">
                  <strong className="text-yellow-300">COMPLIANCE REPORT</strong>
                  {scriptData.planner_report.compliance_rewrites > 0 && (
                    <span>
                      {scriptData.planner_report.compliance_rewrites} passage(s) rewritten to remove
                      unsupported claims: {(scriptData.planner_report.compliance_flags ?? []).join(", ")}
                    </span>
                  )}
                  {scriptData.planner_report.cta_appended && (
                    <span>
                      The writer omitted the call to action, so it was added to the final shot. Review that
                      shot before rendering.
                    </span>
                  )}
                </div>
              )}
            </Panel>
          )}

          <Panel title="SCENE BREAKDOWN" subtitle="EDIT ANY SHOT BEFORE SPENDING RENDER BUDGET" className="w-full">
            <div className="flex flex-col gap-3 p-1 max-h-[560px] overflow-y-auto pr-2">
              {scriptData.script.map((scene: any, idx: number) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.03 }}
                  className="p-4 bg-black/40 border border-white/8 rounded flex flex-col gap-3"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono font-bold text-[var(--color-accent)] bg-[var(--color-accent)]/10 px-2 py-0.5 rounded border border-[var(--color-accent)]/20 shrink-0">
                      SCENE {idx + 1}
                    </span>
                    <input
                      type="text"
                      value={scene.location ?? ""}
                      onChange={(e) => updateScene(idx, "location", e.target.value)}
                      placeholder="Location (required)"
                      aria-label={`Scene ${idx + 1} location`}
                      className="input-field flex-1 text-xs"
                    />
                  </div>

                  {/* Who is on screen. Selecting here is what the render actually
                      uses, so it is a control rather than a static tag list. */}
                  <div className="flex flex-col gap-1">
                    <label className="text-[9px] uppercase font-mono tracking-wider text-[var(--color-accent)]/70">
                      On screen (max 3)
                    </label>
                    <div className="flex gap-1.5 flex-wrap">
                      {(scriptData.characters ?? []).map((c: any) => {
                        const active = (scene.characters_involved ?? []).includes(c.name);
                        return (
                          <button
                            key={c.name}
                            onClick={() => toggleSceneCharacter(idx, c.name)}
                            aria-pressed={active}
                            className={`text-[9px] font-mono px-2 py-1 rounded border transition-all cursor-pointer ${
                              active
                                ? "bg-[var(--color-accent-secondary)]/15 text-[var(--color-accent-secondary)] border-[var(--color-accent-secondary)]/40"
                                : "border-white/10 text-white/35 hover:border-white/30 hover:text-white/60"
                            }`}
                          >
                            {active ? "✓ " : "+ "}{c.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="text-[9px] uppercase font-mono tracking-wider text-[var(--color-accent)]/70">
                      Action — one continuous shot
                    </label>
                    <textarea
                      value={scene.drama_beat ?? ""}
                      onChange={(e) => updateScene(idx, "drama_beat", e.target.value)}
                      placeholder="What the camera sees, in present tense."
                      aria-label={`Scene ${idx + 1} action`}
                      className="input-field text-xs h-16 resize-none font-sans"
                    />
                  </div>

                  {/* Dialogue */}
                  <div className="flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[9px] uppercase font-mono tracking-wider text-[var(--color-accent)]/70">
                        Dialogue (max 2 lines)
                      </label>
                      {(scene.dialogues?.length ?? 0) < 2 && (scene.characters_involved?.length ?? 0) > 0 && (
                        <button
                          onClick={() => addDialogue(idx)}
                          className="text-[9px] font-mono text-white/40 hover:text-[var(--color-accent)] transition-colors cursor-pointer"
                        >
                          + ADD LINE
                        </button>
                      )}
                    </div>
                    {(scene.dialogues ?? []).map((d: any, di: number) => (
                      <div key={di} className="flex gap-1.5 items-center">
                        <select
                          value={d.character_name ?? ""}
                          onChange={(e) => updateDialogue(idx, di, "character_name", e.target.value)}
                          aria-label={`Scene ${idx + 1} line ${di + 1} speaker`}
                          className="input-field text-[10px] w-32 shrink-0"
                        >
                          <option value="">Speaker…</option>
                          {(scene.characters_involved ?? []).map((name: string) => (
                            <option key={name} value={name}>{name}</option>
                          ))}
                        </select>
                        <input
                          type="text"
                          value={d.line ?? d.text ?? ""}
                          onChange={(e) => updateDialogue(idx, di, "line", e.target.value)}
                          placeholder="Spoken line (12 words or fewer)"
                          aria-label={`Scene ${idx + 1} line ${di + 1} text`}
                          className="input-field flex-1 text-xs"
                        />
                        <button
                          onClick={() => removeDialogue(idx, di)}
                          aria-label={`Remove line ${di + 1} from scene ${idx + 1}`}
                          className="text-red-500/50 hover:text-red-400 text-xs px-1.5 cursor-pointer transition-colors"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* Per-shot media. Only image assets are offered: Omni takes
                      images as subject references, and offering audio or video
                      here would imply an influence the renderer does not apply. */}
                  {imageAssets.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <label className="text-[9px] uppercase font-mono tracking-wider text-[var(--color-accent)]/70">
                        Attach media to this shot
                      </label>
                      <div className="flex gap-1.5 flex-wrap">
                        {imageAssets.map((asset) => {
                          const active = (scene.scene_asset_labels ?? []).includes(asset.label);
                          return (
                            <button
                              key={asset.id}
                              onClick={() => toggleSceneAsset(idx, asset.label)}
                              aria-pressed={active}
                              title={`${asset.label} · ${asset.mime_type}`}
                              className={`flex items-center gap-1.5 text-[9px] font-mono px-2 py-1 rounded border transition-all cursor-pointer ${
                                active
                                  ? "bg-[#7c5cd8]/15 text-[#b9a5f0] border-[#7c5cd8]/50"
                                  : "border-white/10 text-white/35 hover:border-white/30 hover:text-white/60"
                              }`}
                            >
                              {asset.thumbnail_b64 ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={asset.thumbnail_b64} alt="" className="w-4 h-4 rounded object-cover" />
                              ) : (
                                <span>🖼</span>
                              )}
                              {active ? "✓ " : ""}{asset.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          </Panel>

          {/* Blocking problems are listed before the render button, because these
              same rules silently drop a shot server-side during a paid render. */}
          {scriptIssues.length > 0 && (
            <div className="w-full p-3 rounded border border-red-500/30 bg-red-500/5 font-mono text-[10px] text-red-300/90 flex flex-col gap-1">
              <strong className="text-red-300">FIX BEFORE RENDERING ({scriptIssues.length})</strong>
              {scriptIssues.slice(0, 8).map((issue) => (
                <span key={issue}>• {issue}</span>
              ))}
              {scriptIssues.length > 8 && <span>…and {scriptIssues.length - 8} more.</span>}
            </div>
          )}

          <div className="w-full flex flex-col items-center gap-2 mt-2 mb-16">
            <div className="flex justify-center gap-4 flex-wrap">
              <button
                onClick={() => setScriptData(null)}
                className="py-3 px-8 border border-white/15 text-white/50 font-mono text-sm hover:text-white hover:border-white/40 transition-all rounded cursor-pointer"
              >
                ← REVISE CAST
              </button>
              <motion.button
                onClick={handleRenderMovie}
                disabled={isRendering || scriptIssues.length > 0}
                whileHover={isRendering || scriptIssues.length > 0 ? {} : { scale: 1.02 }}
                whileTap={isRendering || scriptIssues.length > 0 ? {} : { scale: 0.98 }}
                title={scriptIssues.length > 0 ? "Resolve the listed problems first" : "Render this script"}
                className={`py-4 px-12 rounded font-[family-name:var(--font-family-display)] text-xl tracking-widest transition-all shadow-2xl ${
                  isRendering || scriptIssues.length > 0 ? "opacity-40 cursor-not-allowed" : "cursor-pointer"
                }`}
                style={{ backgroundColor: "var(--color-accent)", color: "black", boxShadow: "0 0 40px color-mix(in srgb, var(--color-accent) 30%, transparent)" }}
              >
                {isRendering ? "⏳ SUBMITTING…" : "🎬 APPROVE & RENDER"}
              </motion.button>
            </div>
            <p className="text-[10px] font-mono text-white/30">
              {scriptData.edited ? "✎ Script edited — your changes will be rendered." : "Script as written by the agents."}
              {" "}{scriptData.script.length} clips will be generated.
            </p>
          </div>
        </div>
        <Footer />
      </AppShell>
    );
  }

  /* ════════════════════════════════════════════
     MAIN STUDIO SETUP VIEW
     ════════════════════════════════════════════ */
  return (
    <AppShell
      header={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-3">
            <Link href="/" className="font-[family-name:var(--font-family-display)] text-xl tracking-widest text-[var(--color-accent)] hover:opacity-80 transition-opacity">
              REVERIE
            </Link>
            <span className="text-white/20 font-mono text-xs">/</span>
            <span className="font-mono text-xs uppercase tracking-widest text-white/50">DIRECTOR STUDIO</span>
          </div>
          <div className="flex items-center gap-4">
            <Badge label={`${readyCount} CHARACTER${readyCount !== 1 ? "S" : ""}`} variant="accent" />
            <Badge label={`${mediaAssets.filter((a) => !a.uploading && !a.error).length} ASSETS`} variant="secondary" />
            <Link href="/" className="text-xs font-mono text-white/40 hover:text-white transition-colors ml-2">
              [EXIT]
            </Link>
          </div>
        </div>
      }
    >
      <div className="flex flex-col items-center py-4 gap-6 w-full max-w-6xl mx-auto">

        {/* ── Page title ── */}
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="text-3xl md:text-4xl tracking-widest font-[family-name:var(--font-family-display)]" style={{ color: "var(--color-accent)" }}>
            REVERIE STUDIO
          </h1>
          <p className="font-mono text-xs text-white/40 max-w-xl">
            Configure your cast, attach visual assets, and let the AI agents improvise your film.
            Powered by <span className="text-[var(--color-accent)]">Gemini Omni</span> — max 10s clips.
          </p>
        </div>

        {/* ── Quick-start presets ── */}
        <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-3">
          {PRESET_TEMPLATES.map((preset) => (
            <button
              key={preset.id}
              onClick={() => applyPreset(preset.id)}
              className={`p-4 rounded border text-left transition-all cursor-pointer group ${
                activePreset === preset.id
                  ? "border-[var(--color-accent)] bg-[var(--color-accent)]/8 shadow-[0_0_24px_color-mix(in_srgb,var(--color-accent)_15%,transparent)]"
                  : "border-white/8 bg-black/30 hover:border-white/20 hover:bg-black/50"
              }`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xl">{preset.icon}</span>
                <span className="font-[family-name:var(--font-family-display)] text-sm font-bold text-[var(--color-accent)] tracking-wider">
                  {preset.name}
                </span>
                {activePreset === preset.id && <Badge label="ACTIVE" variant="accent" />}
              </div>
              <p className="text-[10px] font-mono text-white/40 leading-relaxed line-clamp-2">{preset.premise}</p>
              <p className="text-[9px] font-mono text-white/25 mt-1">{preset.characters.length} CHARACTERS · VISUAL DESCRIPTIONS INCLUDED</p>
            </button>
          ))}
        </div>

        {/* ── Main tab panel ── */}
        <div className="w-full flex flex-col gap-0">
          {/* Tab bar */}
          <div className="flex border-b border-white/10 mb-0">
            {(["cast", "assets", "settings"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-5 py-3 font-mono text-xs uppercase tracking-widest transition-all cursor-pointer border-b-2 -mb-px ${
                  activeTab === tab
                    ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                    : "border-transparent text-white/40 hover:text-white/70"
                }`}
              >
                {tab === "cast" && `🎭 CAST (${readyCount})`}
                {tab === "assets" && `📁 MEDIA ASSETS (${mediaAssets.filter((a) => !a.uploading && !a.error).length})`}
                {tab === "settings" && "⚙ PRODUCTION"}
              </button>
            ))}
          </div>

          {/* ══ CAST TAB ══ */}
          <AnimatePresence mode="wait">
            {activeTab === "cast" && (
              <motion.div key="cast" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
                className="flex flex-col gap-4 pt-4">

                {/* AI Generator */}
                <Panel title="✦ AI CAST GENERATOR" subtitle="DESCRIBE YOUR STORY — AI BUILDS THE WORLD">
                  <div className="flex flex-col md:flex-row gap-4 p-1">
                    <div className="flex-1 flex flex-col gap-2">
                      <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80">Your Premise</label>
                      <textarea
                        value={aiPremise}
                        onChange={(e) => setAiPremise(e.target.value)}
                        placeholder="e.g., A detective in 1940s noire Paris uncovers a conspiracy that goes all the way to the top..."
                        className="bg-black/50 border border-white/15 rounded px-3 py-2.5 text-sm font-sans text-white h-24 focus:border-[var(--color-accent)] outline-none resize-none placeholder:text-white/20"
                      />
                    </div>
                    <div className="flex flex-col gap-3 min-w-[200px]">
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80">Characters</label>
                        <div className="flex gap-2">
                          {[2, 3, 4, 5].map((n) => (
                            <button key={n} onClick={() => setAiCharCount(n)}
                              className={`w-10 h-10 rounded border font-mono text-sm cursor-pointer transition-all ${
                                aiCharCount === n ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)]" : "border-white/10 text-white/50 hover:border-white/30"
                              }`}>{n}</button>
                          ))}
                        </div>
                      </div>
                      <motion.button
                        onClick={handleAiGenerate} disabled={isGenerating}
                        whileHover={isGenerating ? {} : { scale: 1.02 }} whileTap={isGenerating ? {} : { scale: 0.97 }}
                        className={`py-3 px-4 rounded font-mono text-sm uppercase tracking-wider cursor-pointer flex items-center justify-center gap-2 transition-all ${
                          isGenerating ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]/40" : "bg-[var(--color-accent)] text-black font-bold hover:brightness-110"
                        }`}
                      >
                        {isGenerating ? (
                          <><span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin inline-block" /> GENERATING…</>
                        ) : "✦ GENERATE CAST"}
                      </motion.button>
                    </div>
                  </div>
                </Panel>

                {/* Character cards */}
                <AnimatePresence>
                  {characters.map((char, i) => (
                    <motion.div key={i} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}
                      className="rounded border border-white/10 bg-black/30 overflow-hidden"
                    >
                      {/* Card header — always visible */}
                      <button
                        onClick={() => setExpandedChar(expandedChar === i ? -1 : i)}
                        className="w-full flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-white/3 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <span className="text-[10px] font-mono text-white/30 uppercase tracking-wider">#{i + 1}</span>
                          {char.reference_image_base64 ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={char.reference_image_base64} alt="" className="w-7 h-7 rounded-full object-cover border border-white/20" />
                          ) : (
                            <div className="w-7 h-7 rounded-full border border-white/10 bg-white/5 flex items-center justify-center text-xs text-white/20">?</div>
                          )}
                          <span className={`font-[family-name:var(--font-family-display)] text-base ${char.name.trim() ? "text-[var(--color-accent)]" : "text-white/25 italic"}`}>
                            {char.name.trim() || "Unnamed character"}
                          </span>
                          {char.name.trim() && <StatusDot status={char.mood ? "active" : "idle"} label={char.mood || ""} />}
                        </div>
                        <div className="flex items-center gap-3">
                          {char.current_location && <span className="text-[10px] font-mono text-white/30 hidden md:block">{char.current_location}</span>}
                          {characters.length > 1 && (
                            <button onClick={(e) => { e.stopPropagation(); removeCharacter(i); }}
                              className="text-xs font-mono text-red-500/50 hover:text-red-400 transition-colors px-2 py-1 cursor-pointer">
                              [REMOVE]
                            </button>
                          )}
                          <span className="text-white/30 text-xs">{expandedChar === i ? "▲" : "▼"}</span>
                        </div>
                      </button>

                      {/* Expanded form */}
                      <AnimatePresence>
                        {expandedChar === i && (
                          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}
                            className="overflow-hidden border-t border-white/8">
                            <div className="p-4 grid grid-cols-1 md:grid-cols-[1fr_1fr_110px] gap-4">
                              {/* Main fields */}
                              <div className="md:col-span-2 flex flex-col gap-3">
                                <div className="grid grid-cols-2 gap-3">
                                  <Field label="Character Name *">
                                    <input type="text" value={char.name} onChange={(e) => updateCharacter(i, "name", e.target.value)} placeholder="e.g., Detective Moreau"
                                      className="input-field" />
                                  </Field>
                                  <Field label="Initial Location">
                                    <input type="text" value={char.current_location} onChange={(e) => updateCharacter(i, "current_location", e.target.value)} placeholder="e.g., Rain-soaked alley"
                                      className="input-field" />
                                  </Field>
                                </div>
                                <Field label="System Prompt (Personality & Role)">
                                  <textarea value={char.personality_description} onChange={(e) => updateCharacter(i, "personality_description", e.target.value)}
                                    placeholder="Who is this character? How do they speak? What drives them..."
                                    className="input-field h-16 resize-none" />
                                </Field>
                                <Field label="Visual Description for Omni (20–40 words)">
                                  <textarea value={char.visual_description} onChange={(e) => updateCharacter(i, "visual_description", e.target.value)}
                                    placeholder="Injected verbatim into every video prompt — be specific about age, hair, costume, build..."
                                    className="input-field h-14 resize-none" />
                                </Field>
                                <div className="grid grid-cols-2 gap-3">
                                  <Field label="Current Goal">
                                    <input type="text" value={char.current_goal} onChange={(e) => updateCharacter(i, "current_goal", e.target.value)} placeholder="What are they trying to do?"
                                      className="input-field" />
                                  </Field>
                                  <Field label="Current Mood">
                                    <input type="text" value={char.mood} onChange={(e) => updateCharacter(i, "mood", e.target.value)} placeholder="e.g., Determined, Cold, Anxious"
                                      className="input-field" />
                                  </Field>
                                </div>
                                <Field label="Native Omni Audio">
                                  <div className="input-field min-h-10 flex items-center text-xs text-white/45 leading-relaxed">
                                    Dialogue and ambience are generated natively by Omni from the approved shot plan.
                                  </div>
                                </Field>
                                <Field label="Initial Memories (one per line)">
                                  <textarea value={char.memory_stream} onChange={(e) => updateCharacter(i, "memory_stream", e.target.value)}
                                    placeholder={"I witnessed something I shouldn't have.\nI have a score to settle.\nI trust no one completely."}
                                    className="input-field h-20 resize-none" />
                                </Field>
                              </div>

                              {/* Reference image */}
                              <div className="flex flex-col gap-2 items-center">
                                <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-70 text-center">
                                  Character Ref
                                </label>
                                {char.reference_image_base64 ? (
                                  <div className="relative group">
                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                    <img src={char.reference_image_base64} alt={char.name} className="w-[100px] h-[100px] object-cover rounded border border-white/20 shadow-lg" />
                                    <button onClick={() => updateCharacter(i, "reference_image_base64", "")}
                                      className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full text-white text-[10px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">✕</button>
                                  </div>
                                ) : (
                                  <button onClick={() => charImgRefs.current[i]?.click()}
                                    className="w-[100px] h-[100px] rounded border border-dashed border-white/15 flex flex-col items-center justify-center text-white/25 hover:border-[var(--color-accent)]/40 hover:text-[var(--color-accent)]/60 transition-all cursor-pointer">
                                    <span className="text-2xl mb-1">📷</span>
                                    <span className="text-[9px] font-mono">UPLOAD</span>
                                  </button>
                                )}
                                <input ref={(el) => { charImgRefs.current[i] = el; }} type="file" accept="image/*" className="hidden"
                                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCharImage(i, f); e.target.value = ""; }} />
                                <p className="text-[8px] font-mono text-white/25 text-center">CAST LOCK · fed to Omni as a subject reference</p>
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </motion.div>
                  ))}
                </AnimatePresence>

                <button onClick={addCharacter}
                  className="w-full py-3 border border-dashed border-white/15 text-white/40 font-mono text-xs uppercase tracking-widest hover:border-[var(--color-accent)]/40 hover:text-[var(--color-accent)]/60 transition-all cursor-pointer rounded">
                  + ADD CHARACTER
                </button>
              </motion.div>
            )}

            {/* ══ ASSETS TAB ══ */}
            {activeTab === "assets" && (
              <motion.div key="assets" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
                className="flex flex-col gap-4 pt-4">
                <Panel title="📁 MEDIA ASSETS" subtitle="IMAGE SUBJECT REFERENCES · PRODUCTION LIBRARY">
                  <div className="flex flex-col gap-4 p-1">
                    <p className="text-xs text-white/45 font-mono leading-relaxed">
                      Character images are the strongest continuity control. To use an uploaded image as a cast lock,
                      rename its label to exactly match that character&apos;s name. Images labelled anything else can be
                      attached to individual shots in the script editor after the table read. Audio and video uploads
                      stay in the production library and are not sent to Omni, because this API version accepts only
                      images as references.
                    </p>

                    {/* Drop zone */}
                    <div
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => { e.preventDefault(); handleAssetUpload(e.dataTransfer.files); }}
                      onClick={() => assetInputRef.current?.click()}
                      className="border-2 border-dashed border-white/15 rounded-lg p-8 flex flex-col items-center justify-center gap-3 cursor-pointer hover:border-[var(--color-accent)]/40 hover:bg-[var(--color-accent)]/3 transition-all group"
                    >
                      <div className="text-3xl group-hover:scale-110 transition-transform">📎</div>
                      <div className="text-center">
                        <p className="font-mono text-sm text-white/60 group-hover:text-white/80 transition-colors">Drop files here or click to browse</p>
                        <p className="font-mono text-[10px] text-white/30 mt-1">Images become cast locks when labelled with a character name · Up to 20 MB each</p>
                      </div>
                      <input
                        ref={assetInputRef}
                        type="file"
                        multiple
                        accept="image/*,video/mp4,video/webm,video/quicktime,audio/mpeg,audio/mp4,audio/wav,audio/ogg"
                        className="hidden"
                        onChange={(e) => { handleAssetUpload(e.target.files); e.target.value = ""; }}
                      />
                    </div>

                    {/* Asset grid */}
                    {mediaAssets.length > 0 && (
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                        <AnimatePresence>
                          {mediaAssets.map((asset) => (
                            <motion.div key={asset.id} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                              className={`relative flex flex-col rounded border overflow-hidden group ${
                                asset.error ? "border-red-500/30 bg-red-500/5" : asset.uploading ? "border-white/10 bg-black/30" : "border-white/10 bg-black/40 hover:border-white/25"
                              }`}
                            >
                              {/* Thumbnail or placeholder */}
                              <div className="w-full aspect-square bg-black/50 flex items-center justify-center overflow-hidden">
                                {asset.thumbnail_b64 ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img src={asset.thumbnail_b64} alt={asset.label} className="w-full h-full object-cover" />
                                ) : (
                                  <div className="flex flex-col items-center gap-1 text-white/20">
                                    <span className="text-2xl">{asset.uploading ? "⏳" : asset.error ? "⚠️" : assetIcon(asset.asset_type)}</span>
                                    <span className="text-[9px] font-mono uppercase">{asset.asset_type}</span>
                                  </div>
                                )}
                                {asset.uploading && (
                                  <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
                                    <span className="w-6 h-6 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin inline-block" />
                                  </div>
                                )}
                              </div>

                              {/* Info */}
                              <div className="p-2 flex flex-col gap-0.5">
                                <input
                                  type="text"
                                  value={asset.label}
                                  onChange={(e) => setMediaAssets((a) => a.map((x) => x.id === asset.id ? { ...x, label: e.target.value } : x))}
                                  className="bg-transparent text-[10px] font-mono text-white/70 truncate outline-none focus:text-white w-full"
                                  placeholder="Label…"
                                  disabled={asset.uploading}
                                />
                                <span className="text-[9px] font-mono text-white/25">{asset.size_kb} KB · {asset.mime_type.split("/")[1]?.toUpperCase()}</span>
                                {asset.error && <span className="text-[9px] font-mono text-red-400">Upload failed</span>}
                              </div>

                              {/* Remove button */}
                              {!asset.uploading && (
                                <button onClick={() => removeAsset(asset.id)}
                                  className="absolute top-1.5 right-1.5 w-5 h-5 bg-black/70 rounded-full text-white/50 hover:text-red-400 hover:bg-red-500/20 text-[10px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
                                  ✕
                                </button>
                              )}
                            </motion.div>
                          ))}
                        </AnimatePresence>
                      </div>
                    )}

                    {mediaAssets.length === 0 && (
                      <div className="text-center py-4">
                        <p className="font-mono text-xs text-white/25">No assets attached yet. Add a per-character reference image for strongest cast continuity.</p>
                      </div>
                    )}
                  </div>
                </Panel>

                {/* How assets are used */}
                <Panel title="HOW ASSETS INFLUENCE GENERATION" subtitle="REVERIE PIPELINE">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-1">
                    {[
                      { icon: "🖼", title: "Cast Lock", desc: "An image labelled with a character's exact name is sent to Omni as a subject reference for that character." },
                      { icon: "🔗", title: "Stateful Chain", desc: "Each shot branches from the previous accepted shot when the renderer accepts that parent. When it does not, continuity falls back to the character bible and carried-forward state, and the Screening Room labels the shot accordingly." },
                      { icon: "🛡", title: "Continuity Gate", desc: "Each rendered shot is sent to the Director for an identity and adherence check. Shots it approves are marked approved; shots it cannot verify are marked unverified rather than being presented as reviewed." },
                    ].map((item) => (
                      <div key={item.title} className="p-3 rounded bg-black/30 border border-white/8 flex flex-col gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xl">{item.icon}</span>
                          <span className="font-mono text-xs font-bold text-[var(--color-accent)] uppercase tracking-wider">{item.title}</span>
                        </div>
                        <p className="text-xs text-white/50 font-sans leading-relaxed">{item.desc}</p>
                      </div>
                    ))}
                  </div>
                </Panel>
              </motion.div>
            )}

            {/* ══ SETTINGS TAB ══ */}
            {activeTab === "settings" && (
              <motion.div key="settings" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}
                className="flex flex-col gap-4 pt-4">
                <Panel title="⚙ PRODUCTION SETTINGS" subtitle="CINEMATIC OUTPUT CONFIGURATION">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 p-1">

                    {/* Film duration — ad styles show seconds, drama shows minutes */}
                    <div className="flex flex-col gap-2">
                      <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80">
                        🎬 {isAd ? "Ad Duration" : "Total Film Duration"}
                      </label>
                      <div className="grid grid-cols-2 gap-1.5">
                        {(isAd ? AD_DURATION_OPTIONS : FILM_DURATION_OPTIONS).map((opt) => (
                          <button key={opt.value} onClick={() => setFilmDuration(opt.value)}
                            className={`px-2 py-2.5 rounded border text-center text-xs font-mono transition-all cursor-pointer ${
                              filmDuration === opt.value ? "border-[var(--color-accent)] bg-[var(--color-accent)]/15 text-[var(--color-accent)] font-bold" : "border-white/10 text-white/50 hover:border-white/25"
                            }`}>
                            <div className="font-bold">{opt.label}</div>
                            <div className="text-[9px] opacity-60 mt-0.5">{opt.desc}</div>
                          </button>
                        ))}
                      </div>
                      <p className="text-[9px] font-mono text-white/25 mt-0.5">
                        ≈ {totalClips} clip{totalClips !== 1 ? "s" : ""} will be generated
                        {isAd && <span className="text-yellow-400/60"> · Ad mode</span>}
                      </p>
                    </div>

                    {/* Clip duration */}
                    <div className="flex flex-col gap-2">
                      <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80">✂ Per-Clip Length</label>
                      <div className="flex flex-col gap-1.5">
                        {CLIP_DURATION_OPTIONS.map((opt) => (
                          <Chip key={opt.value} selected={videoDuration === opt.value} onClick={() => setVideoDuration(opt.value)}>
                            <span className="font-bold">{opt.label}</span>
                            <span className="opacity-55 ml-2">{opt.desc}</span>
                          </Chip>
                        ))}
                      </div>
                      <p className="text-[9px] font-mono text-[var(--color-accent)]/60 mt-0.5">Omni max: 10 seconds</p>
                    </div>

                    {/* Aspect ratio */}
                    <div className="flex flex-col gap-2">
                      <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80">Aspect Ratio</label>
                      <div className="flex flex-col gap-1.5">
                        {ASPECT_RATIO_OPTIONS.map((opt) => (
                          <Chip key={opt.value} selected={aspectRatio === opt.value} onClick={() => setAspectRatio(opt.value)}>
                            <span className="font-bold">{opt.label}</span>
                            <span className="opacity-55 ml-2">{opt.desc}</span>
                          </Chip>
                        ))}
                      </div>
                    </div>

                    {/* Visual style */}
                    <div className="flex flex-col gap-2">
                      <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80">Visual Style</label>
                      <div className="flex flex-col gap-1.5">
                        {STYLE_OPTIONS.map((opt) => (
                          <Chip key={opt.value} selected={visualStyle === opt.value} onClick={() => {
                            setVisualStyle(opt.value);
                            // Reset duration to sensible default when switching style
                            if (AD_STYLES.has(opt.value)) {
                              setFilmDuration(20); // default 20-second ad
                            } else if (AD_STYLES.has(visualStyle)) {
                              setFilmDuration(1);  // back to 1 minute for drama
                            }
                          }}>
                            <span>{opt.icon}</span>
                            <span className="font-bold ml-1">{opt.label}</span>
                            <span className="opacity-55 ml-2">{opt.desc}</span>
                          </Chip>
                        ))}
                      </div>
                    </div>
                  </div>
                </Panel>

                {/* Summary */}
                <div className="p-4 rounded border border-white/8 bg-black/30 font-mono text-xs flex flex-wrap gap-x-6 gap-y-2 text-white/40">
                  <span>Characters: <strong className="text-[var(--color-accent)]">{readyCount}</strong></span>
                  <span>Assets: <strong className="text-[var(--color-accent)]">{mediaAssets.filter((a) => !a.uploading && !a.error).length}</strong></span>
                  <span>Film: <strong className="text-[var(--color-accent)]">{filmDuration} {isAd ? "sec" : "min"}</strong></span>
                  <span>Clips: <strong className="text-[var(--color-accent)]">{totalClips} × {videoDuration}</strong></span>
                  <span>Ratio: <strong className="text-[var(--color-accent)]">{aspectRatio}</strong></span>
                  <span>Style: <strong className="text-[var(--color-accent)]">{visualStyle}</strong></span>
                  <span>Engine: <strong className="text-[var(--color-accent-secondary)]">Gemini Omni</strong></span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* ── Launch button ── */}
        <div className="w-full flex flex-col items-center gap-3 mt-2 mb-16">
          {readyCount === 0 && (
            <p className="text-xs font-mono text-red-400/60">Add at least one character with a name before launching.</p>
          )}
          <motion.button
            onClick={handleStartSimulation}
            disabled={isStarting || readyCount === 0}
            whileHover={isStarting || readyCount === 0 ? {} : { scale: 1.02 }}
            whileTap={isStarting || readyCount === 0 ? {} : { scale: 0.98 }}
            className={`py-5 px-16 rounded font-[family-name:var(--font-family-display)] text-xl tracking-widest transition-all shadow-2xl cursor-pointer ${
              isStarting || readyCount === 0 ? "opacity-40" : ""
            }`}
            style={{
              backgroundColor: "var(--color-accent)",
              color: "black",
              boxShadow: "0 0 40px color-mix(in srgb, var(--color-accent) 30%, transparent)",
            }}
          >
            {isStarting ? (startingStep || "⏳ INITIALIZING…") : "▶ START SIMULATION ENGINE"}
          </motion.button>
          <p className="text-[10px] font-mono text-white/25">
            {readyCount} character{readyCount !== 1 ? "s" : ""} ·{" "}
            {mediaAssets.filter((a) => !a.uploading && !a.error).length} asset{mediaAssets.filter((a) => !a.uploading && !a.error).length !== 1 ? "s" : ""} ·{" "}
            {filmDuration} {isAd ? "sec" : "min"} · {videoDuration} clips · {aspectRatio} · {visualStyle}
          </p>
        </div>
      </div>
      <Footer />
    </AppShell>
  );
}

/* ─── Tiny helper for labeled form fields ─── */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-70">{label}</label>
      {children}
    </div>
  );
}
