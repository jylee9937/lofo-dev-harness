# Mirroring a wireflow into a design tool

The flow JSON is the source of truth. The design tool shows the same screens, arrows and review marks, so the user can review visuals and UX in one place.

## Rules for every tool

- **Frames**: one frame per screen, named `<number> <title>`, for example `03.01 신청서`. Group frames by stage in flow order: one row or section per stage. Put variants (empty, loading, error, success) next to their main screen.
- **Arrows**: draw each action from the element that triggers it (or the frame edge) to the target frame. Add numbered labels along the scenario the user is reviewing. Mark a `to: null` action with a red "?" stub instead of guessing a target.
- **Review marks**: small labels next to each frame, with the same meanings and colors as the HTML board.

  | Mark | Color | Source in the flow |
  |---|---|---|
  | 기획 근거 / Rationale | teal | `rationale` |
  | 결정 대기 / Open decision | amber | `decisions` with `status: open` |
  | UX S1–S4 | red, orange, yellow, gray | `issues` with `status: open` or `accepted` |
  | 수정 요청 / Change request | pink | `requests` with `status: open` |
  | AI 추정 / AI inferred | purple, dashed frame border | `origin: inferred` |

- **Separate layer**: put arrows and marks in their own layer, section or group named "UX review". It can then be hidden for a pure visual review.
- **Images**: export each screen frame as PNG to `<docs.flows>/images/<flow id>/<screen id>.png`. Set `image` on that screen in the flow. The HTML board can then switch between wireframe and design.
- **Privacy**: `design.ref` holds only a file key, page or frame name. Never put a local path or a personal account in the flow.
- **Changes**: make edits in the flow JSON first, then update the tool. When the user changes something in the tool directly, copy that change back into the flow before the next review round.

## Figma

Use the Figma plugin or MCP server for Claude Code.

- **Skills to load first**:
  - always load `figma:figma-use` before any `use_figma` call
  - in FigJam, load `figma:figma-use-figjam`
  - when composing screens from a design system, use `figma:figma-generate-design`
- **Arrows**:
  - Figma Design files: put frames inside one Section per stage and draw arrows as vector lines with arrowheads. Design files have no native connectors.
  - FigJam: use native connectors between frames.
- **Review marks**: use native annotations on the frame when the API offers them, with the mark name and text. Otherwise, use small auto-layout label frames in the "UX review" section.
- **Images**: export frames to PNG, for example with the screenshot or export tool, into the images folder.
- **Permission**: a Figma file is cloud content. Writing to it is an external write, so confirm with the user before the first write. Never overwrite frames you did not create without asking.

## Pencil (`.pen`)

- **Access**: `.pen` files are encrypted. Never Read or Grep them; use only the Pencil MCP tools.
- **Instructions**: read the Pencil MCP's own instructions first (`read_skill`). Follow its schema for `execute`.
- **Layout**: same as above. Use frames per screen grouped by stage, arrow or connector nodes, and label nodes for marks inside a "UX review" group.
- **Images**: export frame images to the images folder when the tool supports it.
- **Permission**: Pencil files are local, so no confirmation is needed. Ask before restructuring or deleting existing frames.

## Any other tool

This covers tools such as Sketch, Penpot, Framer, Adobe XD and paper sketches.

- **Images**: export each screen to the images folder and set `image`. The HTML board then becomes the review surface for the real design, with the same arrows and marks.
- **Comments**: if the tool has comments or annotations, mirror open issues and change requests there by screen number.
