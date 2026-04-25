import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const SLIDE = { width: 1920, height: 1080 };
const OUT_DIR = "docs";
const PREVIEW_DIR = `${OUT_DIR}/presentation-previews`;

async function loadArtifactTool() {
  try {
    return await import("@oai/artifact-tool");
  } catch {
    const nodePath = process.env.NODE_PATH;
    if (!nodePath) {
      throw new Error(
        "Cannot resolve @oai/artifact-tool. Set NODE_PATH to the bundled node_modules path.",
      );
    }
    const require = createRequire(import.meta.url);
    const resolved = require.resolve("@oai/artifact-tool", {
      paths: nodePath.split(":"),
    });
    return await import(pathToFileURL(resolved).href);
  }
}

const {
  Presentation,
  PresentationFile,
  row,
  column,
  grid,
  panel,
  text,
  shape,
  rule,
  fill,
  hug,
  fixed,
  wrap,
  grow,
  fr,
  auto,
} = await loadArtifactTool();

const colors = {
  ink: "#121821",
  slate: "#4B5563",
  paper: "#F8FAFC",
  dark: "#09111F",
  blue: "#2563EB",
  cyan: "#22D3EE",
  amber: "#F59E0B",
  red: "#EF4444",
  green: "#10B981",
  violet: "#7C3AED",
  line: "#CBD5E1",
};

const heading = {
  fontFace: "Aptos Display",
  bold: true,
  color: colors.ink,
};

const body = {
  fontFace: "Aptos",
  color: colors.slate,
};

function addSlide(presentation, bg = colors.paper) {
  const slide = presentation.slides.add();
  slide.background.fill.color = bg;
  return slide;
}

function compose(slide, tree) {
  slide.compose(tree, {
    frame: { left: 0, top: 0, width: SLIDE.width, height: SLIDE.height },
    baseUnit: 8,
  });
}

function smallLabel(value, color = colors.slate) {
  return text(value, {
    width: fill,
    height: hug,
    style: {
      ...body,
      fontSize: 20,
      bold: true,
      color,
      letterSpacing: 0,
    },
  });
}

function title(value, subtitle, opts = {}) {
  return column(
    { name: "title-stack", width: fill, height: hug, gap: 18 },
    [
      text(value, {
        name: "title",
        width: wrap(opts.width ?? 1260),
        height: hug,
        style: {
          ...heading,
          fontSize: opts.size ?? 62,
          color: opts.color ?? colors.ink,
          letterSpacing: 0,
        },
      }),
      subtitle
        ? text(subtitle, {
            name: "subtitle",
            width: wrap(opts.subtitleWidth ?? 1180),
            height: hug,
            style: {
              ...body,
              fontSize: opts.subtitleSize ?? 28,
              color: opts.subtitleColor ?? colors.slate,
              lineSpacingMultiple: 1.1,
              letterSpacing: 0,
            },
          })
        : rule({
            name: "title-rule",
            width: fixed(180),
            stroke: opts.ruleColor ?? colors.blue,
            weight: 5,
          }),
    ].filter(Boolean),
  );
}

function pill(value, accent) {
  return panel(
    {
      name: `pill-${value.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      width: hug,
      height: hug,
      fill: "#FFFFFF",
      line: { width: 1, fill: "#E2E8F0" },
      borderRadius: "rounded-full",
      padding: { x: 22, y: 12 },
    },
    row({ width: hug, height: hug, gap: 12, align: "center" }, [
      shape({
        name: "pill-dot",
        geometry: "ellipse",
        width: fixed(12),
        height: fixed(12),
        fill: accent,
        line: { width: 0, fill: accent },
      }),
      text(value, {
        width: hug,
        height: hug,
        style: { ...body, fontSize: 20, bold: true, color: colors.ink },
      }),
    ]),
  );
}

function node(label, accent, note = "") {
  return panel(
    {
      name: `node-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      width: fill,
      height: fixed(84),
      fill: "#FFFFFF",
      line: { width: 1, fill: "#D7E0EA" },
      borderRadius: "rounded-lg",
      padding: { x: 18, y: 14 },
    },
    row({ width: fill, height: fill, gap: 14, align: "center" }, [
      shape({
        name: "node-accent",
        width: fixed(8),
        height: fill,
        fill: accent,
        line: { width: 0, fill: accent },
      }),
      column({ width: fill, height: hug, gap: 4 }, [
        text(label, {
          width: fill,
          height: hug,
          style: { ...heading, fontSize: 24, color: colors.ink },
        }),
        note
          ? text(note, {
              width: fill,
              height: hug,
              style: { ...body, fontSize: 16, color: colors.slate },
            })
          : null,
      ].filter(Boolean)),
    ]),
  );
}

function evidenceRow(left, right, accent) {
  return row(
    { width: fill, height: hug, gap: 22, align: "center", padding: { y: 3 } },
    [
      shape({
        name: "row-dot",
        width: fixed(12),
        height: fixed(12),
        geometry: "ellipse",
        fill: accent,
        line: { width: 0, fill: accent },
      }),
      text(left, {
        width: fixed(490),
        height: hug,
        style: { ...heading, fontSize: 28, color: colors.ink },
      }),
      text(right, {
        width: fill,
        height: hug,
        style: { ...body, fontSize: 23, color: colors.slate, lineSpacingMultiple: 1.08 },
      }),
    ],
  );
}

function scoreBar(label, score, widthPx, accent, side = "left") {
  const bar = shape({
    name: `${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-bar`,
    width: fixed(widthPx),
    height: fixed(48),
    fill: accent,
    line: { width: 0, fill: accent },
  });
  const empty = shape({
    name: "score-bar-spacer",
    width: fill,
    height: fixed(48),
    fill: "#EEF2F7",
    line: { width: 0, fill: "#EEF2F7" },
  });
  const lane =
    side === "left"
      ? row({ width: fixed(430), height: fixed(48), gap: 0, align: "center" }, [empty, bar])
      : row({ width: fixed(430), height: fixed(48), gap: 0, align: "center" }, [bar, empty]);

  return row({ width: fill, height: hug, gap: 18, align: "center" }, [
    text(label, {
      width: fixed(210),
      height: hug,
      style: { ...heading, fontSize: 24, color: colors.ink },
    }),
    lane,
    text(score, {
      width: fixed(110),
      height: hug,
      style: { ...heading, fontSize: 28, color: accent },
    }),
  ]);
}

function buildDeck() {
  const presentation = Presentation.create({ slideSize: SLIDE });

  const cover = addSlide(presentation, colors.dark);
  compose(
    cover,
    grid(
      {
        name: "cover-root",
        width: fill,
        height: fill,
        columns: [fr(1.05), fr(0.95)],
        rows: [fr(1)],
        columnGap: 80,
        padding: { x: 104, y: 82 },
        alignItems: "center",
      },
      [
        column({ width: fill, height: hug, gap: 26, justify: "center" }, [
          text("BlastRadius", {
            name: "cover-title",
            width: fill,
            height: hug,
            style: {
              fontFace: "Aptos Display",
              fontSize: 104,
              bold: true,
              color: "#FFFFFF",
              letterSpacing: 0,
            },
          }),
          text("Hidden-lineage incident diagnosis for agentic RL", {
            width: wrap(780),
            height: hug,
            style: {
              ...body,
              fontSize: 34,
              color: "#C8D4E3",
              lineSpacingMultiple: 1.05,
            },
          }),
          rule({ width: fixed(240), stroke: colors.cyan, weight: 6 }),
          row({ width: hug, height: hug, gap: 16 }, [
            pill("OpenReward", colors.cyan),
            pill("ORS server", colors.green),
            pill("Docker-ready", colors.amber),
          ]),
        ]),
        column({ width: fill, height: hug, gap: 24, justify: "center" }, [
          text("The agent sees tools.", {
            width: fill,
            height: hug,
            style: { ...heading, fontSize: 50, color: "#FFFFFF" },
          }),
          text("The reward asks whether it inferred the system.", {
            width: fill,
            height: hug,
            style: { ...body, fontSize: 32, color: "#C8D4E3" },
          }),
          column({ width: fill, height: hug, gap: 14, padding: { y: 18 } }, [
            rule({ width: fill, stroke: "#334155", weight: 2 }),
            row({ width: fill, height: hug, gap: 20, align: "center" }, [
              text("raw.orders_api", {
                width: fixed(315),
                height: hug,
                style: { ...body, fontSize: 22, color: "#E2E8F0" },
              }),
              rule({ width: grow(1), stroke: colors.cyan, weight: 4 }),
              text("dashboard.revenue", {
                width: fixed(340),
                height: hug,
                style: { ...body, fontSize: 22, color: "#E2E8F0" },
              }),
            ]),
            row({ width: fill, height: hug, gap: 20, align: "center" }, [
              text("mart.marketing_roi", {
                width: fixed(315),
                height: hug,
                style: { ...body, fontSize: 22, color: "#E2E8F0" },
              }),
              rule({ width: grow(1), stroke: colors.amber, weight: 4 }),
              text("cloud cost spike", {
                width: fixed(340),
                height: hug,
                style: { ...body, fontSize: 22, color: "#E2E8F0" },
              }),
            ]),
            row({ width: fill, height: hug, gap: 20, align: "center" }, [
              text("partial lineage", {
                width: fixed(315),
                height: hug,
                style: { ...body, fontSize: 22, color: "#E2E8F0" },
              }),
              rule({ width: grow(1), stroke: colors.violet, weight: 4 }),
              text("delayed reward", {
                width: fixed(340),
                height: hug,
                style: { ...body, fontSize: 22, color: "#E2E8F0" },
              }),
            ]),
            rule({ width: fill, stroke: "#334155", weight: 2 }),
          ]),
        ]),
      ],
    ),
  );

  const challenge = addSlide(presentation);
  compose(
    challenge,
    column({ width: fill, height: fill, padding: { x: 104, y: 76 }, gap: 54 }, [
      title(
        "Not an alert-routing task.",
        "BlastRadius scores whether an agent can infer the hidden causal graph while the platform keeps changing.",
      ),
      grid(
        {
          width: fill,
          height: fill,
          columns: [fr(1), fr(1)],
          rows: [fr(1)],
          columnGap: 70,
          alignItems: "center",
        },
        [
          column({ width: fill, height: hug, gap: 30 }, [
            evidenceRow(
              "Partial observability",
              "Logs, samples, schemas, job history, and query plans each reveal only part of the incident.",
              colors.blue,
            ),
            evidenceRow(
              "Non-stationarity",
              "Hidden incidents fire during the episode, so a static diagnosis is not enough.",
              colors.amber,
            ),
            evidenceRow(
              "Root cause pressure",
              "Symptom-only fixes can make a dashboard look better while leaving reward on the floor.",
              colors.red,
            ),
          ]),
          panel(
            {
              width: fill,
              height: fixed(560),
              fill: "#FFFFFF",
              line: { width: 1, fill: "#E2E8F0" },
              borderRadius: "rounded-lg",
              padding: { x: 42, y: 42 },
            },
            column({ width: fill, height: fill, gap: 28, justify: "center" }, [
              smallLabel("CANONICAL FAILURE MODE", colors.red),
              text("A competent agent should resist the obvious dashboard fix.", {
                width: fill,
                height: hug,
                style: { ...heading, fontSize: 46, color: colors.ink, lineSpacingMultiple: 1.02 },
              }),
              text(
                "The naive baseline repeatedly treats leaf symptoms. It terminates early with both incidents unresolved.",
                {
                  width: fill,
                  height: hug,
                  style: { ...body, fontSize: 27, color: colors.slate, lineSpacingMultiple: 1.08 },
                },
              ),
              row({ width: fill, height: hug, gap: 36, align: "end" }, [
                column({ width: fixed(230), height: hug, gap: 5 }, [
                  text("-164.9", {
                    width: fill,
                    height: hug,
                    style: { ...heading, fontSize: 56, color: colors.red },
                  }),
                  smallLabel("baseline score"),
                ]),
                column({ width: fixed(230), height: hug, gap: 5 }, [
                  text("0 / 2", {
                    width: fill,
                    height: hug,
                    style: { ...heading, fontSize: 56, color: colors.red },
                  }),
                  smallLabel("incidents fixed"),
                ]),
              ]),
            ]),
          ),
        ],
      ),
    ]),
  );

  const environment = addSlide(presentation);
  compose(
    environment,
    column({ width: fill, height: fill, padding: { x: 104, y: 74 }, gap: 36 }, [
      title(
        "The v1 substrate is small enough to verify, but rich enough to reason over.",
        "Eight deterministic nodes, two hidden incidents, eleven operational tools, reward emitted as deltas per tool call.",
        { width: 1540, subtitleWidth: 1380, size: 54 },
      ),
      grid(
        {
          width: fill,
          height: fill,
          columns: [fr(1.35), fr(0.85)],
          rows: [fr(1)],
          columnGap: 44,
        },
        [
          grid(
            {
              width: fill,
              height: fill,
              columns: [fr(1), fr(1), fr(1), fr(1)],
              rows: [auto, auto, auto],
              columnGap: 18,
              rowGap: 18,
              alignItems: "stretch",
            },
            [
              node("raw.orders_api", colors.blue, "schema drift"),
              node("raw.ad_spend", colors.blue),
              node("raw.web_events", colors.blue),
              node("stg.orders", colors.violet),
              node("stg.marketing", colors.violet),
              node("mart.revenue", colors.green),
              node("mart.marketing_roi", colors.amber, "cost explosion"),
              node("dashboard.exec", colors.green, "leaf SLA"),
              text("Lineage is discovered through tools, not handed to the agent.", {
                columnSpan: 4,
                width: fill,
                height: hug,
                style: { ...body, fontSize: 24, color: colors.slate },
              }),
            ],
          ),
          panel(
            {
              width: fill,
              height: fill,
              fill: "#FFFFFF",
              line: { width: 1, fill: "#E2E8F0" },
              borderRadius: "rounded-lg",
              padding: { x: 34, y: 34 },
            },
            column({ width: fill, height: fill, gap: 24 }, [
              smallLabel("TOOL SURFACE", colors.blue),
              text("11 tools", {
                width: fill,
                height: hug,
                style: { ...heading, fontSize: 58, color: colors.ink },
              }),
              text("Schemas, samples, logs, lineage traces, tests, fixes, and wait actions each carry cost and latency.",
                {
                  width: fill,
                  height: hug,
                  style: { ...body, fontSize: 24, color: colors.slate, lineSpacingMultiple: 1.08 },
                }),
              rule({ width: fill, stroke: "#E2E8F0", weight: 2 }),
              smallLabel("EPISODE"),
              text("tick 0 -> 250", {
                width: fill,
                height: hug,
                style: { ...heading, fontSize: 42, color: colors.ink },
              }),
              smallLabel("TASKS"),
              text("80 train / 20 eval seeds", {
                width: fill,
                height: hug,
                style: { ...heading, fontSize: 36, color: colors.ink },
              }),
            ]),
          ),
        ],
      ),
    ]),
  );

  const evidence = addSlide(presentation);
  compose(
    evidence,
    column({ width: fill, height: fill, padding: { x: 104, y: 74 }, gap: 42 }, [
      title(
        "The calibration trace separates symptom patching from causal repair.",
        "Seed 0 gives a compact demo: same environment, same hidden incidents, different policy behavior.",
        { width: 1500, subtitleWidth: 1380, size: 54 },
      ),
      grid(
        {
          width: fill,
          height: fill,
          columns: [fr(1.05), fr(0.95)],
          columnGap: 56,
          alignItems: "center",
        },
        [
          panel(
            {
              width: fill,
              height: fixed(520),
              fill: "#FFFFFF",
              line: { width: 1, fill: "#E2E8F0" },
              borderRadius: "rounded-lg",
              padding: { x: 34, y: 34 },
            },
            column({ width: fill, height: fill, gap: 28, justify: "center" }, [
              smallLabel("SCORE BY POLICY", colors.blue),
              scoreBar("Naive baseline", "-164.9", 390, colors.red, "left"),
              scoreBar("Competent path", "5.6", 34, colors.green, "right"),
              row({ width: fill, height: hug, gap: 20, align: "center" }, [
                text("symptom patching", {
                  width: fill,
                  height: hug,
                  style: { ...body, fontSize: 22, color: colors.slate },
                }),
                rule({ width: fixed(150), stroke: "#94A3B8", weight: 2 }),
                text("causal repair", {
                  width: fill,
                  height: hug,
                  style: { ...body, fontSize: 22, color: colors.slate },
                }),
              ]),
            ]),
          ),
          column({ width: fill, height: hug, gap: 28 }, [
            row({ width: fill, height: hug, gap: 28 }, [
              panel(
                {
                  width: fill,
                  height: fixed(170),
                  fill: "#FFFFFF",
                  line: { width: 1, fill: "#E2E8F0" },
                  borderRadius: "rounded-lg",
                  padding: { x: 26, y: 24 },
                },
                column({ width: fill, height: hug, gap: 8 }, [
                  text("170.5", {
                    width: fill,
                    height: hug,
                    style: { ...heading, fontSize: 58, color: colors.green },
                  }),
                  smallLabel("score delta"),
                ]),
              ),
              panel(
                {
                  width: fill,
                  height: fixed(170),
                  fill: "#FFFFFF",
                  line: { width: 1, fill: "#E2E8F0" },
                  borderRadius: "rounded-lg",
                  padding: { x: 26, y: 24 },
                },
                column({ width: fill, height: hug, gap: 8 }, [
                  text("15", {
                    width: fill,
                    height: hug,
                    style: { ...heading, fontSize: 58, color: colors.ink },
                  }),
                  smallLabel("scripted tool calls"),
                ]),
              ),
            ]),
            evidenceRow(
              "Baseline",
              "Wrong diagnosis at tick 85, no incidents resolved, fatal score collapse.",
              colors.red,
            ),
            evidenceRow(
              "Competent path",
              "Finds schema drift, verifies downstream health, fixes cost explosion, monitors to tick 250.",
              colors.green,
            ),
          ]),
        ],
      ),
    ]),
  );

  const demo = addSlide(presentation, "#FFFFFF");
  compose(
    demo,
    column({ width: fill, height: fill, padding: { x: 104, y: 76 }, gap: 48 }, [
      title(
        "What the hackathon demo should show.",
        "A public OpenReward environment plus one model rollout is enough to tell the story in 2-3 minutes.",
        { width: 1400, subtitleWidth: 1320, size: 58 },
      ),
      grid(
        {
          width: fill,
          height: fill,
          columns: [fr(1), fr(1), fr(1)],
          columnGap: 28,
          alignItems: "stretch",
        },
        [
          panel(
            {
              width: fill,
              height: fill,
              fill: "#F8FAFC",
              line: { width: 1, fill: "#E2E8F0" },
              borderRadius: "rounded-lg",
              padding: { x: 34, y: 34 },
            },
            column({ width: fill, height: fill, gap: 18 }, [
              smallLabel("1", colors.blue),
              text("OpenReward page", {
                width: fill,
                height: hug,
                style: { ...heading, fontSize: 38, color: colors.ink },
              }),
              text("Make the environment public, show the README card, and confirm train/eval splits plus the tool list.",
                {
                  width: fill,
                  height: hug,
                  style: { ...body, fontSize: 25, color: colors.slate, lineSpacingMultiple: 1.08 },
                }),
            ]),
          ),
          panel(
            {
              width: fill,
              height: fill,
              fill: "#F8FAFC",
              line: { width: 1, fill: "#E2E8F0" },
              borderRadius: "rounded-lg",
              padding: { x: 34, y: 34 },
            },
            column({ width: fill, height: fill, gap: 18 }, [
              smallLabel("2", colors.amber),
              text("Model rollout", {
                width: fill,
                height: hug,
                style: { ...heading, fontSize: 38, color: colors.ink },
              }),
              text("Run GPT-5.5 or Opus 4.7 against seed 0 and compare its behavior to the scripted calibration.",
                {
                  width: fill,
                  height: hug,
                  style: { ...body, fontSize: 25, color: colors.slate, lineSpacingMultiple: 1.08 },
                }),
            ]),
          ),
          panel(
            {
              width: fill,
              height: fill,
              fill: "#F8FAFC",
              line: { width: 1, fill: "#E2E8F0" },
              borderRadius: "rounded-lg",
              padding: { x: 34, y: 34 },
            },
            column({ width: fill, height: fill, gap: 18 }, [
              smallLabel("3", colors.green),
              text("Capability claim", {
                width: fill,
                height: hug,
                style: { ...heading, fontSize: 38, color: colors.ink },
              }),
              text("The key capability is causal diagnosis under partial observability, not just calling many tools.",
                {
                  width: fill,
                  height: hug,
                  style: { ...body, fontSize: 25, color: colors.slate, lineSpacingMultiple: 1.08 },
                }),
            ]),
          ),
        ],
      ),
      text("Repo path: hashkanna/blast-radius  |  Docker image: OpenReward ORS server on port 8080", {
        width: fill,
        height: hug,
        style: { ...body, fontSize: 18, color: "#64748B" },
      }),
    ]),
  );

  return presentation;
}

async function saveBlob(blob, path) {
  if (typeof blob.save === "function") {
    await blob.save(path);
    return;
  }
  const buffer = Buffer.from(await blob.arrayBuffer());
  await writeFile(path, buffer);
}

await mkdir(PREVIEW_DIR, { recursive: true });
const deck = buildDeck();
const pptx = await PresentationFile.exportPptx(deck);
await saveBlob(pptx, `${OUT_DIR}/blastradius-hackathon-presentation.pptx`);

for (let index = 0; index < deck.slides.count; index += 1) {
  const slide = deck.slides.getItem(index);
  const png = await slide.export({ format: "png", width: SLIDE.width, height: SLIDE.height });
  await saveBlob(png, `${PREVIEW_DIR}/slide-${String(index + 1).padStart(2, "0")}.png`);
}

console.log(`Wrote ${OUT_DIR}/blastradius-hackathon-presentation.pptx`);
console.log(`Wrote ${deck.slides.count} previews to ${PREVIEW_DIR}`);
