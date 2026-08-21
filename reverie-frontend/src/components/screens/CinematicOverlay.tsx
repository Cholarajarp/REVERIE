"use client";

/**
 * CinematicOverlay — fullscreen studio monitor for live Gemini Omni feeds.
 *
 * Two structural notes:
 *
 * 1. Astryx `Overlay` is NOT a modal. Its own docs describe it as a scrim over
 *    media, the same composition pattern as Tooltip. `Dialog variant="fullscreen"`
 *    is the correct primitive: it renders a real <dialog>, so we inherit focus
 *    trapping, Escape handling, scroll lock and aria-modal for free.
 *
 * 2. Dialog returns null while closed, which unmounts children synchronously and
 *    would kill any exit animation. So the Dialog is held open for the duration
 *    of the exit and only closed on AnimatePresence's onExitComplete.
 */

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { VStack, HStack } from "@astryxdesign/core/Layout";
import { AspectRatio } from "@astryxdesign/core/AspectRatio";
import { Text } from "@astryxdesign/core/Text";
import { Token } from "@astryxdesign/core/Token";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Divider } from "@astryxdesign/core/Divider";
import type { SceneRecord } from "../../store/simulationStore";

// Astryx Stack forwards ref/className/style, so motion can drive it directly.
// This keeps the animation without reintroducing raw <div> layout.
const MotionVStack = motion.create(VStack);

/** Anamorphic scope. Matches the 2.39:1 framing the dashboard advertises. */
const ANAMORPHIC_RATIO = 2.39;

export interface CinematicOverlayProps {
  scene: SceneRecord | null;
  onClose: () => void;
}

export function CinematicOverlay({ scene, onClose }: CinematicOverlayProps) {
  const prefersReducedMotion = useReducedMotion();
  const [isDialogOpen, setIsDialogOpen] = useState(scene !== null);

  // Opening is immediate; closing is deferred to onExitComplete below.
  useEffect(() => {
    if (scene) setIsDialogOpen(true);
  }, [scene]);

  const handleOpenChange = useCallback(
    (open: boolean) => {
      // Fires on Escape and backdrop click. Delegate to the parent so the
      // scene prop is the single source of truth.
      if (!open) onClose();
    },
    [onClose],
  );

  // Only tear the Dialog down if there is genuinely nothing to show. Swapping
  // scene A -> B also fires onExitComplete (A's exit), and closing there would
  // dismiss the monitor while B is still active.
  const handleExitComplete = useCallback(() => {
    if (!scene) setIsDialogOpen(false);
  }, [scene]);

  // Subtle, monitor-like: a short lift and settle, no bounce. Reduced-motion
  // users get the opacity crossfade only.
  const transition = prefersReducedMotion
    ? { duration: 0.2, ease: "linear" as const }
    : { type: "spring" as const, stiffness: 260, damping: 30, mass: 0.9 };

  const variants = prefersReducedMotion
    ? { hidden: { opacity: 0 }, visible: { opacity: 1 } }
    : {
        hidden: { opacity: 0, scale: 0.97, y: 12 },
        visible: { opacity: 1, scale: 1, y: 0 },
      };

  return (
    <Dialog
      isOpen={isDialogOpen}
      onOpenChange={handleOpenChange}
      variant="fullscreen"
      purpose="info"
      aria-label="Cinematic scene monitor"
      className="bg-body"
    >
      <AnimatePresence onExitComplete={handleExitComplete}>
        {scene && (
          <MotionVStack
            key={scene.scene_id}
            height="100%"
            gap={0}
            initial="hidden"
            animate="visible"
            exit="hidden"
            variants={variants}
            transition={transition}
          >
            <DialogHeader
              title={`SCENE // ${scene.scene_id}`}
              subtitle="REVERIE SIMULATION ENGINE — LIVE OMNI FEED"
              onOpenChange={handleOpenChange}
              hasDivider
              endContent={
                <HStack gap={2} align="center">
                  {/* Rendered only when the writer actually scored this beat.
                      `(drama_score ?? 0) * 100` displayed a confident "DRAMA 0%"
                      for any shot that carried no rating at all. */}
                  {scene.drama_score != null && (
                    <Token
                      label={`TENSION ${Math.round(scene.drama_score * 100)}%`}
                      color={scene.drama_score > 0.75 ? "red" : "yellow"}
                      size="sm"
                    />
                  )}
                  <Token label={scene.status.replace(/_/g, " ")} color="gray" size="sm" />
                </HStack>
              }
            />

            <VStack padding={4} gap={4} height="100%" justify="center">
              <AspectRatio ratio={ANAMORPHIC_RATIO} fit="cover" className="bg-inverted rounded-lg overflow-hidden">
                {scene.video_uri ? (
                  <video
                    src={scene.video_uri}
                    autoPlay
                    loop
                    muted
                    playsInline
                    controls
                    aria-label={`Generated footage for scene ${scene.scene_id}`}
                  />
                ) : (
                  <VStack align="center" justify="center" gap={3} height="100%" padding={6}>
                    <Spinner size="lg" shade="onMedia" label="Rendering scene" />
                    <Text type="label" size="sm" color="accent">
                        OMNI GENERATION IN PROGRESS
                    </Text>
                    <Text size="sm" color="secondary" justify="center" maxLines={4}>
                      {scene.omni_prompt || scene.veo_prompt}
                    </Text>
                  </VStack>
                )}
              </AspectRatio>

              <Divider variant="subtle" />

              <HStack gap={3} justify="between" align="start" wrap="wrap">
                <VStack gap={1.5}>
                  <Text type="label" size="xsm" color="secondary">
                    FEATURING AGENTS
                  </Text>
                  <HStack gap={1.5} wrap="wrap">
                    {scene.characters_involved.map((character) => (
                      <Token key={character} label={character} color="blue" size="sm" />
                    ))}
                  </HStack>
                </VStack>
                <Text type="label" size="xsm" color="secondary">
                  2.39:1 ANAMORPHIC
                </Text>
              </HStack>
            </VStack>
          </MotionVStack>
        )}
      </AnimatePresence>
    </Dialog>
  );
}
