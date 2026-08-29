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

/* ─── Ad presets ───
   An advertisement is not a short drama, so it does not start from a dramatic
   ensemble. These are presenters and product demos: small casts, a concrete
   product, and a premise the Ads Specialist can derive a value proposition
   from. Kept separate from PRESET_TEMPLATES so neither list has to pretend to
   serve both jobs. */
const AD_PRESET_TEMPLATES = [
  {
    id: "ad-product",
    name: "Product Launch",
    icon: "📦",
    brand: "Aether Running Shoes",
    premise:
      "A trail runner laces up Aether running shoes before dawn and crests a ridge as the sun breaks, showing the shoe's grip and cushioning",
    characters: [
      { name: "Maya", current_location: "Mountain Trailhead", current_goal: "Reach the ridge before sunrise.", mood: "Focused and calm", memory_stream: "I run this trail every morning.\nThese shoes changed how far I can go.", personality_description: "You are Maya, a trail runner who speaks plainly and never oversells. You describe how something feels, not how great it is.", voice_id: "en-US-Neural2-E", visual_description: "Athletic woman, early 30s, dark ponytail, wearing a teal running jacket and black leggings, bright orange trail running shoes", reference_image_base64: "" },
    ],
  },
  {
    id: "ad-app",
    name: "App / Service Demo",
    icon: "📱",
    brand: "Ledger",
    premise:
      "A small cafe owner uses the Ledger app to close out her books in under a minute at the end of a long shift",
    characters: [
      { name: "Priya", current_location: "Cafe Counter", current_goal: "Finish the books and get home.", mood: "Tired but relieved", memory_stream: "I used to spend an hour on this every night.\nNow it takes a minute on my phone.", personality_description: "You are Priya, a cafe owner. You are warm, practical, and talk about time saved rather than features.", voice_id: "en-US-Neural2-F", visual_description: "South Asian woman, late 30s, hair in a loose bun, wearing a denim apron over a mustard shirt, warm tired smile", reference_image_base64: "" },
    ],
  },
  {
    id: "ad-food",
    name: "Food & Beverage",
    icon: "☕",
    brand: "Rooted Coffee",
    premise:
      "Slow macro shots of Rooted Coffee being poured at sunrise while a barista describes where the beans come from",
    characters: [
      { name: "Theo", current_location: "Roastery Bar", current_goal: "Pour the morning's first cup.", mood: "Unhurried and warm", memory_stream: "I have poured this blend a thousand times.\nI know the farm it comes from.", personality_description: "You are Theo, a barista who speaks slowly and specifically about origin and craft. You never use marketing language.", voice_id: "en-US-Studio-O", visual_description: "Man, late 20s, close beard, forearm tattoo, wearing a charcoal apron over a white tee, behind a wooden roastery bar", reference_image_base64: "" },
    ],
  },
];

/* ─── Configuration Options ─── */
const CLIP_DURATION_OPTIONS = [
  { value: "10s", label: "10 sec", desc: "Stateful Omni shot" },
];

/* Duration is a continuous range, not a fixed menu.
   Both tracks are bounded by the same hard limits the backend enforces, so the
   control cannot express a production the render would reject:
     - clips are atomic 10s Omni shots (OMNI_CLIP_DURATION_SECONDS)
     - the daily budget is 24 clips = 240s of footage
   Ads are expressed in SECONDS and drama in MINUTES, matching the units
   `studio_engine.simulate_script` branches on via `is_ad_style`. */
const CLIP_SECONDS = 10;
/* The renderer reserves one clip per shot against a daily budget
   (OMNI_DAILY_CLIP_BUDGET, default 24). Scene CRUD is capped by this so the
   editor cannot build a script the render would reject outright. */
const MAX_SCENES = 24;
const AD_DURATION_RANGE = { min: 10, max: 90, step: 10 };   // seconds
const FILM_DURATION_RANGE = { min: 1, max: 4, step: 1 };     // minutes

const ASPECT_RATIO_OPTIONS = [
  { value: "16:9", label: "16:9", desc: "Standard HD (Omni default)" },
  { value: "9:16", label: "9:16", desc: "Vertical / mobile" },
];

const STYLE_OPTIONS = [
  { value: "cinematic", label: "Cinematic", desc: "Film-quality realism", icon: "🎬" },
  { value: "anime", label: "Anime", desc: "Japanese animation", icon: "✨" },
  { value: "documentary", label: "Documentary", desc: "Raw, grounded", icon: "📹" },
  { value: "noir", label: "Noir", desc: "High-contrast shadow", icon: "🌑" },
  // "commercial" is deliberately absent. Advertising is a production MODE, not a
  // look: it swaps the planner (Ads Specialist, not the drama screenwriter), the
  // unit of duration, and the validation rules. Burying it in this list forced a
  // choice between telling a story and selling a product.
];

const AD_VISUAL_STYLE = "commercial";

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
  /* Brand/product name for ad styles. Sent to the Ads Specialist as a brief
     hint; ignored by the drama screenwriter. */
  const [brand, setBrand] = useState("");
  /* Production mode is the top-level fork: it decides which planner runs, what
     unit duration is expressed in, and which presets and validation apply.
     It maps onto the backend's existing `visual_style`-based `is_ad_style`
     check, so no new backend contract is introduced. */
  const [productionMode, setProductionMode] = useState<"film" | "ad">("film");

  /* Cast */
  const [characters, setCharacters] = useState<CharacterData[]>([emptyCharacter()]);
  const [activePreset, setActivePreset] = useState<string | null>(null);
  const [expandedChar, setExpandedChar] = useState<number>(0);

  /* Media assets */
  const [mediaAssets, setMediaAssets] = useState<MediaAsset[]>([]);
  const assetInputRef = useRef<HTMLInputElement>(null);
  /* Separate input for the review screen: the assets tab is unmounted by then,
     so its ref is unavailable while the script is being approved. */
  const reviewAssetInputRef = useRef<HTMLInputElement>(null);
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

  /* ── Derived production values ──
     Declared above the handlers because the request payloads below depend on
     them. `filmDuration` carries different units per mode, exactly as the
     backend reads it: SECONDS for ads, MINUTES for film. Keeping the conversion
     in one place stops the slider bounds and the clip estimate from drifting
     apart.

     Ad-ness is decided by the production MODE, not by the aesthetic. It still
     travels to the backend as `visual_style: "commercial"`, which is what
     `is_ad_style` already keys on, so no new backend contract is needed. */
  const isAd = productionMode === "ad";
  const effectiveVisualStyle = isAd ? AD_VISUAL_STYLE : visualStyle;
  const durationRange = isAd ? AD_DURATION_RANGE : FILM_DURATION_RANGE;
  const targetSeconds = isAd ? filmDuration : filmDuration * 60;
  const totalClips = Math.max(1, Math.ceil(targetSeconds / CLIP_SECONDS));
  const activePresetList = isAd ? AD_PRESET_TEMPLATES : PRESET_TEMPLATES;

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
    // Look in the list for the CURRENT mode, so an ad preset can never be
    // applied to a film production or vice versa.
    const preset = activePresetList.find((p) => p.id === id);
    if (!preset) return;
    setCharacters(preset.characters as CharacterData[]);
    setAiPremise(preset.premise);
    // Ad presets carry the brand they are selling; film presets have none.
    if ("brand" in preset && typeof preset.brand === "string") setBrand(preset.brand);
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
        body: JSON.stringify({ premise: aiPremise, num_characters: aiCharCount, visual_style: effectiveVisualStyle, film_duration_minutes: filmDuration }),
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
      /* `targetSeconds` is written because `filmDuration` alone is ambiguous:
         it means minutes for a film and seconds for an ad. The dashboard read it
         as minutes unconditionally, so a 30s ad was computed as 180 clips and its
         progress bar sat near zero for the whole render. */
      sessionStorage.setItem("reverie_settings", JSON.stringify({
        videoDuration,
        filmDuration,
        targetSeconds,
        isAd,
        aspectRatio,
        visualStyle: effectiveVisualStyle,
      }));
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
            visual_style: effectiveVisualStyle,
            premise: aiPremise,
            // Only meaningful in ad mode; the drama planner ignores it.
            brand: isAd ? brand.trim() : "",
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
        // Normalise dialogue key: the backend may return `text` or `line`.
        // The editor always writes to `line`, so unify on load.
        if (data.script) {
          data.script = data.script.map((scene: any) => ({
            ...scene,
            dialogues: (scene.dialogues ?? []).map((d: any) => ({
              ...d,
              line: d.line ?? d.text ?? "",
            })),
          }));
        }
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
        const defaultSpeaker =
          scene.characters_involved?.[0] ??
          (isAd ? "Voiceover" : (prev.characters?.[0]?.name ?? "Voiceover"));
        return { ...scene, dialogues: [...dialogues, { character_name: defaultSpeaker, line: "" }] };
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

  /* ── Scene CRUD ──
     Adding or removing shots changes the film's real length. The compiler passes
     `target_duration_seconds` to ffmpeg as `-t`, which TRIMS the output, so a
     script that grew without updating it would render clips the viewer never
     sees — billed, then cut. Every structural edit therefore rewrites the
     runtime to match the shot count. */
  const withSyncedRuntime = (prev: any, script: any[]) => {
    const seconds = script.length * CLIP_SECONDS;
    const settings = { ...(prev.settings ?? {}) };
    settings.target_duration_seconds = seconds;
    // This field carries SECONDS for ads and MINUTES for film, matching the
    // backend's unit convention for the same key.
    settings.film_duration_minutes = AD_STYLES.has(settings.visual_style ?? "")
      ? seconds
      : Math.max(1, Math.round(seconds / 60));
    return { ...prev, script, settings, edited: true };
  };

  /* `transition_from_previous` describes the shot that came BEFORE this one, and
     the cinematographer injects it verbatim as "Continuity transition: ..." into
     the Omni prompt. After a structural edit the predecessor can be a different
     shot entirely, so a stale note would instruct the renderer to match a scene
     that is no longer there. Only the shots whose predecessor actually changed
     are cleared, and shot 1 never carries one. */
  const clearStaleTransitions = (script: any[], indices: number[]) => {
    const affected = new Set(indices.filter((i) => i >= 0 && i < script.length));
    if (script.length > 0) affected.add(0);
    return script.map((scene, i) => {
      if (!affected.has(i)) return scene;
      const continuity = { ...(scene.continuity ?? {}) };
      if (!String(continuity.transition_from_previous ?? "").trim()) return scene;
      continuity.transition_from_previous = "";
      return { ...scene, continuity };
    });
  };

  const emptyScene = () => ({
    location: "",
    drama_beat: "",
    characters_involved: [],
    dialogues: [],
    scene_asset_labels: [],
    continuity: { environment_state: "", transition_from_previous: "", character_state_updates: [] },
  });

  const addScene = (afterIdx?: number) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = [...prev.script];
      if (script.length >= MAX_SCENES) return prev;
      const at = afterIdx === undefined ? script.length : afterIdx + 1;
      script.splice(at, 0, emptyScene());
      // The inserted shot and the one displaced after it both have new predecessors.
      return withSyncedRuntime(prev, clearStaleTransitions(script, [at, at + 1]));
    });

  const duplicateScene = (idx: number) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = [...prev.script];
      if (script.length >= MAX_SCENES) return prev;
      // Deep-copy the nested arrays so editing the copy cannot mutate the original.
      const source = script[idx];
      script.splice(idx + 1, 0, {
        ...source,
        characters_involved: [...(source.characters_involved ?? [])],
        dialogues: (source.dialogues ?? []).map((d: any) => ({ ...d })),
        scene_asset_labels: [...(source.scene_asset_labels ?? [])],
        continuity: { ...(source.continuity ?? {}) },
      });
      // The copy inherited a transition describing the ORIGINAL's predecessor,
      // which is not its own. The shot after it also shifted.
      return withSyncedRuntime(prev, clearStaleTransitions(script, [idx + 1, idx + 2]));
    });

  const removeScene = (idx: number) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const script = prev.script.filter((_: any, i: number) => i !== idx);
      // Whatever followed the deleted shot now follows a different one.
      return withSyncedRuntime(prev, clearStaleTransitions(script, [idx]));
    });

  const moveScene = (idx: number, delta: number) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const target = idx + delta;
      if (target < 0 || target >= prev.script.length) return prev;
      const script = [...prev.script];
      [script[idx], script[target]] = [script[target], script[idx]];
      // Both swapped shots, and the one following the later slot, changed predecessor.
      const lo = Math.min(idx, target);
      const hi = Math.max(idx, target);
      // Order changed but the shot count did not, so runtime is unaffected.
      return {
        ...prev,
        script: clearStaleTransitions(script, [lo, hi, hi + 1]),
        edited: true,
      };
    });

  /* ── Cast CRUD during review ──
     A name is a foreign key: the backend drops any `characters_involved` entry or
     dialogue speaker it cannot match to a cast member. So a rename must cascade
     through every scene, and a removal must clear that character from all shots,
     or the edit silently loses content at render time. */
  const updateReviewCharacter = (idx: number, field: string, value: string) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const characters = [...(prev.characters ?? [])];
      const previousName = String(characters[idx]?.name ?? "");
      characters[idx] = { ...characters[idx], [field]: value };
      if (field !== "name" || value === previousName) {
        return { ...prev, characters, edited: true };
      }
      const script = prev.script.map((scene: any) => ({
        ...scene,
        characters_involved: (scene.characters_involved ?? []).map((n: string) =>
          n === previousName ? value : n
        ),
        dialogues: (scene.dialogues ?? []).map((d: any) =>
          d.character_name === previousName ? { ...d, character_name: value } : d
        ),
      }));
      return { ...prev, characters, script, edited: true };
    });

  const removeReviewCharacter = (idx: number) =>
    setScriptData((prev: any) => {
      if (!prev) return prev;
      const name = String(prev.characters?.[idx]?.name ?? "");
      const characters = (prev.characters ?? []).filter((_: any, i: number) => i !== idx);
      const script = prev.script.map((scene: any) => ({
        ...scene,
        characters_involved: (scene.characters_involved ?? []).filter((n: string) => n !== name),
        dialogues: (scene.dialogues ?? []).filter((d: any) => d.character_name !== name),
      }));
      return { ...prev, characters, script, edited: true };
    });

  /* Validate before spending render budget. These mirror the backend's
     _normalise_scene rules, so a script that would be silently dropped mid-render
     is caught here while it is still free to fix. */
  const scriptIssues: string[] = React.useMemo(() => {
    if (!scriptData?.script) return [];
    const issues: string[] = [];
    // Read ad-ness from the settings the BACKEND returned, which is authoritative
    // for the script under review, and fall back to the current mode.
    const scriptIsAd = AD_STYLES.has(scriptData.settings?.visual_style ?? "") || isAd;
    const castNames = new Set((scriptData.characters ?? []).map((c: any) => c.name));
    scriptData.script.forEach((scene: any, i: number) => {
      const n = i + 1;
      if (!String(scene.location ?? "").trim()) issues.push(`Scene ${n}: location is empty.`);
      if (!String(scene.drama_beat ?? "").trim()) issues.push(`Scene ${n}: action is empty.`);
      if ((scene.characters_involved?.length ?? 0) > 3)
        issues.push(`Scene ${n}: more than 3 characters on screen.`);
      // Only an ad may have a product-only shot with nobody on screen.
      if (!scriptIsAd && (scene.characters_involved?.length ?? 0) === 0)
        issues.push(`Scene ${n}: no characters selected.`);
      if ((scene.dialogues?.length ?? 0) > 2)
        issues.push(`Scene ${n}: more than 2 dialogue lines for a 10s shot.`);
      (scene.dialogues ?? []).forEach((d: any, j: number) => {
        const speaker = String(d.character_name ?? "").trim();
        const isVoRole = /^(voiceover|narrator|announcer|presenter|vo)/i.test(speaker);
        if (!String(d.line ?? "").trim()) {
          issues.push(`Scene ${n}, line ${j + 1}: dialogue text is empty.`);
        } else if (
          !scene.characters_involved?.includes(speaker) &&
          !castNames.has(speaker) &&
          !isVoRole &&
          !scriptIsAd
        ) {
          issues.push(`Scene ${n}, line ${j + 1}: speaker "${speaker}" is not recognized.`);
        }
      });
    });
    // Scene CRUD can grow the script past what the daily clip budget allows.
    // The render would refuse this outright, so it is caught here instead.
    if (scriptData.script.length > MAX_SCENES)
      issues.push(`${scriptData.script.length} scenes exceeds the ${MAX_SCENES}-clip daily render budget.`);
    if (scriptData.script.length === 0)
      issues.push("The script has no scenes.");
    // render_movie refuses a production with no cast, so catch it here rather
    // than letting the render fail after the user has committed to it.
    if ((scriptData.characters?.length ?? 0) === 0)
      issues.push("The production has no cast members.");
    return issues;
  }, [scriptData, isAd]);

  /* ── Render approved script ── */
  const handleRenderMovie = async () => {
    if (scriptIssues.length > 0) {
      alert(`Fix these before rendering:\n\n${scriptIssues.slice(0, 10).join("\n")}`);
      return;
    }
    setIsRendering(true);
    try {
      /* Re-attach the current asset library to every cast entry before rendering.
         The backend resolves each shot's `scene_asset_labels` against
         `characters[*].reference_asset_urls`, and that list is otherwise frozen
         from launch time — so an image uploaded during review would be
         attachable here yet silently resolve to nothing in the render. */
      const liveAssets = mediaAssets
        .filter((a) => !a.uploading && !a.error && a.public_url)
        .map((a) => ({
          url: a.public_url,
          label: a.label,
          type: a.asset_type,
          mime_type: a.mime_type,
        }));
      const renderPayload = {
        ...scriptData,
        settings: {
          ...(scriptData.settings ?? {}),
          aspect_ratio: scriptData.settings?.aspect_ratio ?? aspectRatio,
        },
        characters: (scriptData.characters ?? []).map((c: any) => ({
          ...c,
          reference_asset_urls: liveAssets,
        })),
      };

      const res = await fetch(`${getApiBase()}/api/studio/render_movie`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(renderPayload),
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

          {/* Stats bar with active Aspect Ratio toggle */}
          <div className="w-full flex items-center gap-4 p-3 rounded border border-white/10 bg-black/30 font-mono text-xs text-white/50 flex-wrap">
            <span><strong className="text-[var(--color-accent)]">{scriptData.script.length}</strong> scenes</span>
            <span className="opacity-30">|</span>
            <span><strong className="text-[var(--color-accent)]">{scriptData.settings?.visual_style ?? visualStyle}</strong> style</span>
            <span className="opacity-30">|</span>
            <span><strong className="text-[var(--color-accent)]">{scriptData.settings?.video_duration ?? videoDuration}</strong> per clip</span>
            <span className="opacity-30">|</span>
            <div className="flex items-center gap-1.5">
              <span className="text-white/40">Aspect:</span>
              <div className="flex rounded border border-white/15 overflow-hidden">
                {(["16:9", "9:16"] as const).map((ratio) => {
                  const currentRatio = scriptData.settings?.aspect_ratio ?? aspectRatio;
                  const isSelected = currentRatio === ratio;
                  return (
                    <button
                      key={ratio}
                      onClick={() => {
                        setAspectRatio(ratio);
                        setScriptData((prev: any) => ({
                          ...prev,
                          settings: { ...(prev.settings ?? {}), aspect_ratio: ratio },
                          edited: true,
                        }));
                      }}
                      className={`px-2 py-0.5 text-[10px] font-mono transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-[var(--color-accent)] text-black font-bold"
                          : "bg-white/5 text-white/60 hover:text-white"
                      }`}
                    >
                      {ratio === "9:16" ? "9:16 (Vertical)" : "16:9 (Landscape)"}
                    </button>
                  );
                })}
              </div>
            </div>
            <span className="ml-auto text-[var(--color-accent-secondary)]">Gemini Omni · max 10s clips</span>
          </div>

          {/* ── Campaign brief (commercial productions only) ──
              Shown because an ad is judged against a strategy. The compliance
              report states what the specialist had to rewrite, rather than
              presenting edited copy as the writer's original output. */}
          {scriptData.campaign_brief && (
            <Panel title="📣 CAMPAIGN BRIEF" subtitle="ADS SPECIALIST · EDITABLE BEFORE RENDER" className="w-full">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 p-1 font-mono text-xs">
                {(["brand", "product", "audience", "value_proposition", "tone", "call_to_action"] as const).map((field) => (
                  <div key={field} className="flex flex-col gap-0.5">
                    <span className="text-[9px] uppercase tracking-wider text-[var(--color-accent)]/70">
                      {field.replace(/_/g, " ")}
                    </span>
                    <input
                      type="text"
                      value={scriptData.campaign_brief[field] || ""}
                      onChange={(e) =>
                        setScriptData((prev: any) => ({
                          ...prev,
                          campaign_brief: { ...prev.campaign_brief, [field]: e.target.value },
                        }))
                      }
                      className="bg-white/5 border border-white/10 rounded px-2 py-1 text-white/80 focus:outline-none focus:border-[var(--color-accent)]/50 text-xs font-mono"
                    />
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

          {/* Cast, editable during review.
              A character name is effectively a foreign key: the backend drops any
              on-screen entry or dialogue speaker it cannot match to a cast member.
              Renaming here therefore cascades through every shot, and removing a
              character clears them from all shots, so an edit can never silently
              lose dialogue at render time. */}
          <Panel title="🎭 CAST" subtitle="RENAME OR RETIRE — CHANGES CASCADE THROUGH EVERY SHOT" className="w-full">
            <div className="flex flex-col gap-2 p-1">
              {(scriptData.characters ?? []).map((c: any, ci: number) => (
                <div
                  key={ci}
                  className="flex flex-col md:flex-row gap-2 md:items-center p-2 rounded border border-white/8 bg-black/30"
                >
                  <input
                    type="text"
                    value={c.name ?? ""}
                    onChange={(e) => updateReviewCharacter(ci, "name", e.target.value)}
                    placeholder="Character name"
                    aria-label={`Cast member ${ci + 1} name`}
                    className="input-field text-xs md:w-44 shrink-0"
                  />
                  <input
                    type="text"
                    value={c.visual_description ?? ""}
                    onChange={(e) => updateReviewCharacter(ci, "visual_description", e.target.value)}
                    placeholder="Visual description — injected into every shot prompt"
                    aria-label={`Cast member ${ci + 1} visual description`}
                    className="input-field text-xs flex-1"
                  />
                  <button
                    onClick={() => removeReviewCharacter(ci)}
                    aria-label={`Remove ${c.name || `cast member ${ci + 1}`} from the production`}
                    title="Remove from the production and from every shot"
                    className="text-red-500/50 hover:text-red-400 font-mono text-[10px] px-2 py-1 cursor-pointer transition-colors shrink-0"
                  >
                    REMOVE
                  </button>
                </div>
              ))}
              {(scriptData.characters?.length ?? 0) === 0 && (
                <p className="font-mono text-[10px] text-red-300/70">
                  No cast members left. The render requires at least one.
                </p>
              )}
              <p className="text-[9px] font-mono text-white/25">
                The visual description sits at the top of every Omni prompt, so it is the strongest
                continuity control on this screen.
              </p>
            </div>
          </Panel>

          {/* Asset library, available during review.
              Uploading previously required going back and re-running the table
              read, which discarded the script. Renaming is deliberately not
              offered here: a shot stores the asset LABEL, so a rename at this
              point would silently orphan attachments already made below. */}
          <Panel title="🖼 IMAGE LIBRARY" subtitle="UPLOAD NOW · ATTACH TO ANY SHOT BELOW" className="w-full">
            <div className="flex flex-col gap-3 p-1">
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  onClick={() => reviewAssetInputRef.current?.click()}
                  className="px-4 py-2 rounded border border-dashed border-white/20 text-white/50 font-mono text-[10px] uppercase tracking-wider hover:border-[var(--color-accent)]/50 hover:text-[var(--color-accent)]/80 transition-all cursor-pointer"
                >
                  + ADD IMAGES
                </button>
                <span className="font-mono text-[10px] text-white/30">
                  {imageAssets.length} image{imageAssets.length !== 1 ? "s" : ""} available
                </span>
                <input
                  ref={reviewAssetInputRef}
                  type="file"
                  multiple
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => { handleAssetUpload(e.target.files); e.target.value = ""; }}
                />
              </div>

              {mediaAssets.length > 0 && (
                <div className="flex gap-2 flex-wrap">
                  {mediaAssets.map((asset) => (
                    <div
                      key={asset.id}
                      title={`${asset.label} · ${asset.mime_type}`}
                      className={`flex items-center gap-2 px-2 py-1.5 rounded border font-mono text-[10px] ${
                        asset.error
                          ? "border-red-500/30 bg-red-500/5 text-red-300/70"
                          : "border-white/10 bg-black/30 text-white/60"
                      }`}
                    >
                      {asset.thumbnail_b64 ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={asset.thumbnail_b64} alt="" className="w-6 h-6 rounded object-cover" />
                      ) : (
                        <span className="text-sm">{asset.uploading ? "⏳" : asset.error ? "⚠️" : assetIcon(asset.asset_type)}</span>
                      )}
                      <span className="truncate max-w-[140px]">{asset.label}</span>
                      {!asset.uploading && (
                        <button
                          onClick={() => removeAsset(asset.id)}
                          aria-label={`Remove asset ${asset.label}`}
                          className="text-white/30 hover:text-red-400 transition-colors cursor-pointer"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Panel>

          <Panel title="SCENE BREAKDOWN" subtitle="EDIT ANY SHOT BEFORE SPENDING RENDER BUDGET" className="w-full">
            <div className="flex flex-col gap-3 p-1 max-h-[800px] overflow-y-auto pr-2">
              {scriptData.script.map((scene: any, idx: number) => (
                <motion.div
                  key={scene._id ?? idx}
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
                    {/* Structural controls. Each shot is one billed 10s render, so
                        reordering and deleting here is what stops a bad shot from
                        being paid for. */}
                    <div className="flex items-center gap-0.5 shrink-0">
                      <button
                        onClick={() => moveScene(idx, -1)}
                        disabled={idx === 0}
                        aria-label={`Move scene ${idx + 1} earlier`}
                        title="Move earlier"
                        className={`px-1.5 py-1 text-xs rounded transition-colors ${
                          idx === 0 ? "text-white/12 cursor-not-allowed" : "text-white/40 hover:text-[var(--color-accent)] cursor-pointer"
                        }`}
                      >
                        ↑
                      </button>
                      <button
                        onClick={() => moveScene(idx, 1)}
                        disabled={idx === scriptData.script.length - 1}
                        aria-label={`Move scene ${idx + 1} later`}
                        title="Move later"
                        className={`px-1.5 py-1 text-xs rounded transition-colors ${
                          idx === scriptData.script.length - 1 ? "text-white/12 cursor-not-allowed" : "text-white/40 hover:text-[var(--color-accent)] cursor-pointer"
                        }`}
                      >
                        ↓
                      </button>
                      <button
                        onClick={() => duplicateScene(idx)}
                        disabled={scriptData.script.length >= MAX_SCENES}
                        aria-label={`Duplicate scene ${idx + 1}`}
                        title={scriptData.script.length >= MAX_SCENES ? `Limit is ${MAX_SCENES} scenes` : "Duplicate this shot"}
                        className={`px-1.5 py-1 text-[10px] rounded transition-colors ${
                          scriptData.script.length >= MAX_SCENES ? "text-white/12 cursor-not-allowed" : "text-white/40 hover:text-[var(--color-accent)] cursor-pointer"
                        }`}
                      >
                        ⧉
                      </button>
                      <button
                        onClick={() => addScene(idx)}
                        disabled={scriptData.script.length >= MAX_SCENES}
                        aria-label={`Insert a new scene after scene ${idx + 1}`}
                        title={scriptData.script.length >= MAX_SCENES ? `Limit is ${MAX_SCENES} scenes` : "Insert a shot below"}
                        className={`px-1.5 py-1 text-xs rounded transition-colors ${
                          scriptData.script.length >= MAX_SCENES ? "text-white/12 cursor-not-allowed" : "text-white/40 hover:text-[var(--color-accent)] cursor-pointer"
                        }`}
                      >
                        +
                      </button>
                      <button
                        onClick={() => removeScene(idx)}
                        aria-label={`Delete scene ${idx + 1}`}
                        title="Delete this shot"
                        className="px-1.5 py-1 text-xs rounded text-red-500/50 hover:text-red-400 cursor-pointer transition-colors"
                      >
                        🗑
                      </button>
                    </div>
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

                  {/* Dialogue & Voiceover */}
                  <div className="flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[9px] uppercase font-mono tracking-wider text-[var(--color-accent)]/70">
                        Dialogue / Voiceover (max 2 lines)
                      </label>
                      {(scene.dialogues?.length ?? 0) < 2 && (
                        <button
                          onClick={() => addDialogue(idx)}
                          className="text-[9px] font-mono text-white/40 hover:text-[var(--color-accent)] transition-colors cursor-pointer"
                        >
                          + ADD LINE / VOICEOVER
                        </button>
                      )}
                    </div>
                    {(scene.dialogues?.length ?? 0) === 0 && (
                      <p className="text-[9px] font-mono text-white/25 italic">
                        No dialogue for this shot (ambient / music only). Click &quot;+ ADD LINE / VOICEOVER&quot; if speech is desired.
                      </p>
                    )}
                    {(scene.dialogues ?? []).map((d: any, di: number) => {
                      const allSpeakerOptions = [
                        ...(scene.characters_involved ?? []).map((name: string) => ({ value: name, label: `${name} (On-Screen)` })),
                        ...(scriptData.characters ?? [])
                          .filter((c: any) => !(scene.characters_involved ?? []).includes(c.name))
                          .map((c: any) => ({ value: c.name, label: `${c.name} (Cast)` })),
                        { value: "Voiceover", label: "🎙️ Voiceover (VO)" },
                        { value: "Narrator", label: "🎙️ Narrator" },
                        { value: "Announcer", label: "📢 Announcer" },
                      ];
                      return (
                        <div key={di} className="flex flex-col gap-1 p-2 rounded border border-white/8 bg-black/20">
                          <div className="flex items-center justify-between gap-2">
                            <select
                              value={d.character_name ?? ""}
                              onChange={(e) => updateDialogue(idx, di, "character_name", e.target.value)}
                              aria-label={`Scene ${idx + 1} line ${di + 1} speaker`}
                              className="input-field text-[10px] flex-1"
                            >
                              <option value="">Select speaker…</option>
                              {allSpeakerOptions.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                            <button
                              onClick={() => removeDialogue(idx, di)}
                              aria-label={`Remove line ${di + 1} from scene ${idx + 1}`}
                              className="text-red-500/50 hover:text-red-400 text-xs px-1.5 shrink-0 cursor-pointer transition-colors"
                            >
                              ✕
                            </button>
                          </div>
                          <input
                            type="text"
                            value={d.line ?? ""}
                            onChange={(e) => updateDialogue(idx, di, "line", e.target.value)}
                            placeholder="Spoken line / voiceover text — 12 words or fewer"
                            aria-label={`Scene ${idx + 1} line ${di + 1} text`}
                            className="input-field w-full text-xs"
                          />
                        </div>
                      );
                    })}
                  </div>

                  {/* Per-shot media. Only image assets are offered: Omni takes
                      images as subject references, and offering audio or video
                      here would imply an influence the renderer does not apply. */}
                  {/* Always rendered. This section used to be hidden entirely when
                      the library held no images, so a user who had not uploaded
                      before the table read saw no attach control at all and read
                      it as a missing feature. */}
                  <div className="flex flex-col gap-1">
                    <label className="text-[9px] uppercase font-mono tracking-wider text-[var(--color-accent)]/70">
                      Attach media to this shot
                    </label>
                    {imageAssets.length === 0 ? (
                      <p className="text-[9px] font-mono text-white/30">
                        No images in the library yet — add some above to attach them here.
                      </p>
                    ) : (
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
                    )}
                  </div>
                </motion.div>
              ))}

              {/* Append a shot. Runtime is recalculated from the shot count, so
                  the compiled film is never trimmed shorter than the script. */}
              <button
                onClick={() => addScene()}
                disabled={scriptData.script.length >= MAX_SCENES}
                className={`w-full py-3 border border-dashed rounded font-mono text-xs uppercase tracking-widest transition-all ${
                  scriptData.script.length >= MAX_SCENES
                    ? "border-white/8 text-white/20 cursor-not-allowed"
                    : "border-white/15 text-white/40 hover:border-[var(--color-accent)]/40 hover:text-[var(--color-accent)]/60 cursor-pointer"
                }`}
              >
                {scriptData.script.length >= MAX_SCENES
                  ? `Scene limit reached (${MAX_SCENES})`
                  : "+ ADD SCENE"}
              </button>
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
            {isAd
              ? "Define the product, the presenter, and the runtime. The Ads Specialist writes a campaign brief, then a compliant shot list that ends on your call to action."
              : "Configure your cast, attach visual assets, and let the AI agents improvise your film."}{" "}
            Powered by <span className="text-[var(--color-accent)]">Gemini Omni</span> — max 10s clips.
          </p>
        </div>

        {/* ── Production mode ──
            The top-level fork. Advertising swaps the planner, the unit of
            duration, the presets, and the validation rules, so it is a mode
            rather than one entry in the visual-style list. */}
        <div className="w-full flex flex-col items-center gap-2">
          <div
            role="tablist"
            aria-label="Production mode"
            className="inline-flex rounded border border-white/12 overflow-hidden bg-black/40"
          >
            {([
              { id: "film", label: "🎞 FILM", desc: "Dramatic story" },
              { id: "ad", label: "📣 ADVERTISEMENT", desc: "Product campaign" },
            ] as const).map((m) => (
              <button
                key={m.id}
                role="tab"
                aria-selected={productionMode === m.id}
                onClick={() => {
                  if (productionMode === m.id) return;
                  const nextIsAd = m.id === "ad";
                  setProductionMode(m.id);
                  // Duration units differ per mode (seconds vs minutes), so the
                  // value has to be reset rather than carried across.
                  setFilmDuration(nextIsAd ? 30 : 1);
                  // Presets belong to one mode only; keeping a stale selection
                  // highlighted would imply the other list's cast is loaded.
                  setActivePreset(null);
                  if (!nextIsAd) setBrand("");
                }}
                className={`px-6 py-3 font-mono text-xs uppercase tracking-widest transition-all cursor-pointer ${
                  productionMode === m.id
                    ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)]"
                    : "text-white/40 hover:text-white/70"
                }`}
              >
                <span className="font-bold">{m.label}</span>
                <span className="block text-[9px] opacity-60 tracking-normal mt-0.5">{m.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ── Quick-start presets ── */}
        <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-3">
          {activePresetList.map((preset) => (
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
                          {/* A single-character piece is legitimate: a monologue,
                              a narrator, or a product demo with one presenter. */}
                          {[1, 2, 3, 4, 5].map((n) => (
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

                    {/* Film duration — a draggable range rather than two fixed
                        presets. Ads are set in seconds, drama in minutes, and the
                        bounds mirror what the backend will actually accept. */}
                    <div className="flex flex-col gap-2">
                      <label
                        htmlFor="film-duration-range"
                        className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80"
                      >
                        🎬 {isAd ? "Ad Duration" : "Total Film Duration"}
                      </label>
                      <div className="flex items-baseline gap-2">
                        <span className="font-[family-name:var(--font-family-display)] text-2xl text-[var(--color-accent)] tabular-nums">
                          {filmDuration}
                        </span>
                        <span className="font-mono text-xs text-white/40">{isAd ? "seconds" : "minutes"}</span>
                      </div>
                      <input
                        id="film-duration-range"
                        type="range"
                        min={durationRange.min}
                        max={durationRange.max}
                        step={durationRange.step}
                        value={filmDuration}
                        onChange={(e) => setFilmDuration(Number(e.target.value))}
                        aria-label={isAd ? "Ad duration in seconds" : "Total film duration in minutes"}
                        aria-valuemin={durationRange.min}
                        aria-valuemax={durationRange.max}
                        aria-valuenow={filmDuration}
                        aria-valuetext={`${filmDuration} ${isAd ? "seconds" : "minutes"}`}
                        className="w-full accent-[var(--color-accent)] cursor-pointer"
                      />
                      <div className="flex justify-between font-mono text-[9px] text-white/25">
                        <span>{durationRange.min}{isAd ? "s" : "m"}</span>
                        <span>{durationRange.max}{isAd ? "s" : "m"}</span>
                      </div>
                      <p className="text-[9px] font-mono text-white/25 mt-0.5">
                        {totalClips} clip{totalClips !== 1 ? "s" : ""} × 10s ={" "}
                        {totalClips * 10}s of footage
                        {isAd && <span className="text-yellow-400/60"> · Ad mode</span>}
                      </p>
                      {/* Clips are atomic 10s Omni shots, so a value that is not a
                          multiple of 10 is rounded up. Say so instead of silently
                          rendering a longer film than the number displayed. */}
                      {totalClips * 10 !== targetSeconds && (
                        <p className="text-[9px] font-mono text-yellow-400/50">
                          Rounded up to {totalClips * 10}s — Omni renders whole 10s shots.
                        </p>
                      )}
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

                    {/* Visual style — film mode only.
                        Ad mode sends visual_style="commercial", which the
                        cinematographer maps to its own lighting grammar. Showing
                        aesthetic chips here would be a control that silently does
                        nothing, so the fixed look is stated instead.
                        Switching an aesthetic never changes the duration unit any
                        more, because ad-ness is now the production mode. */}
                    {isAd ? (
                      <div className="flex flex-col gap-2">
                        <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80">Look</label>
                        <div className="p-3 rounded border border-white/10 bg-black/30 font-mono text-[10px] text-white/50 leading-relaxed">
                          <strong className="text-[var(--color-accent)]">Commercial grammar</strong>
                          <span className="block mt-1">
                            Bright high-key lighting, product in crisp focus, stabilised camera.
                            Applied automatically in ad mode.
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <label className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80">Visual Style</label>
                        <div className="flex flex-col gap-1.5">
                          {STYLE_OPTIONS.map((opt) => (
                            <Chip key={opt.value} selected={visualStyle === opt.value} onClick={() => setVisualStyle(opt.value)}>
                              <span>{opt.icon}</span>
                              <span className="font-bold ml-1">{opt.label}</span>
                              <span className="opacity-55 ml-2">{opt.desc}</span>
                            </Chip>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Brand is only asked for when it is actually used. The Ads
                      Specialist takes it as a brief hint; the drama screenwriter
                      has no use for it. */}
                  {isAd && (
                    <div className="flex flex-col gap-1.5 p-1 pt-4 mt-2 border-t border-white/8">
                      <label
                        htmlFor="brand-name"
                        className="text-[10px] uppercase font-mono tracking-wider text-[var(--color-accent)] opacity-80"
                      >
                        📣 Brand / Product Name
                      </label>
                      <input
                        id="brand-name"
                        type="text"
                        value={brand}
                        maxLength={120}
                        onChange={(e) => setBrand(e.target.value)}
                        placeholder="e.g., Aether Running Shoes"
                        className="input-field text-xs max-w-md"
                      />
                      <p className="text-[9px] font-mono text-white/25">
                        Names the product in the campaign brief and on screen. Left blank, the
                        strategist infers it from your premise.
                      </p>
                    </div>
                  )}
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
            {filmDuration} {isAd ? "sec" : "min"} · {videoDuration} clips · {aspectRatio} · {effectiveVisualStyle}
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
