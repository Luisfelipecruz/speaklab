// The types for a static image import — `import talk from "@/assets/talk.png"` giving a
// StaticImageData — come from Next, and Next writes the reference into next-env.d.ts,
// which is generated and not committed. `tsc --noEmit` on a fresh checkout runs before
// anything has generated that file, so the reference is made here as well.
/// <reference types="next/image-types/global" />
