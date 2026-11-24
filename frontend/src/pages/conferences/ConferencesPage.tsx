import {
  FileExcelOutlined,
  FilePdfOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Flex,
  Skeleton,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { CSSProperties, HTMLAttributes } from "react";
import { useSearchParams } from "react-router";

import { conferencesExportUrl } from "../../api/client";
import { useConferences, useRefreshConferences } from "../../api/hooks";
import type {
  ClashGroup,
  Conference,
  ConferencesReport,
} from "../../api/types";
import worldMap from "../../assets/world-map.svg";
import { PageHeader } from "../../components/PageHeader";
import { formatDateTime, formatDay } from "../../lib/format";
import { MoreDetail, ReportTiles } from "../reports/ReportParts";
import "./ConferencesPage.css";

// Priority as in the BD schedule (user decision 2026-11-24): green 1, yellow 2, orange 3.
const PRIORITIES = [1, 2, 3] as const;
const PRIORITY_COLOUR: Record<number, string> = {
  1: "#2EE6A0",
  2: "#FFC24B",
  3: "#FF8A50",
};
const NO_PRIORITY = "#A9B4D0";
const PAST = "#5D6A8A";
// The map image is Natural Earth land (public domain), equirectangular, 180°W–180°E and 83°N–58°S.
const fx = (lon: number) => (lon + 180) / 360;
const fy = (lat: number) => (83 - lat) / 141;
const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
const OCEANS = [
  { label: "PACIFIC\nOCEAN", lon: -140, lat: 10 },
  { label: "ATLANTIC\nOCEAN", lon: -38, lat: 22 },
  { label: "INDIAN\nOCEAN", lon: 78, lat: -22 },
  { label: "PACIFIC\nOCEAN", lon: 165, lat: 15 },
];

function priorityColour(p: number | null): string {
  return p ? (PRIORITY_COLOUR[p] ?? NO_PRIORITY) : NO_PRIORITY;
}

function colourOf(c: Conference): string {
  return c.past ? PAST : priorityColour(c.priority);
}

function priorityLabel(p: number | null): string {
  return p ? `Priority ${p}` : "No priority";
}

function when(c: Conference): string {
  if (c.past) return "Done";
  return c.days_until > 0 ? `In ${c.days_until} days` : "On now";
}

function span(start: string, end: string): string {
  return end !== start
    ? `${formatDay(start)} – ${formatDay(end)}`
    : formatDay(start);
}

function bookedTwice(c: Conference): string[] {
  return [...new Set(c.clashes.flatMap((k) => k.shared))];
}

function Chip({
  on,
  label,
  dot,
  onClick,
}: {
  on: boolean;
  label: string;
  dot?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        minHeight: 34,
        padding: "0 12px",
        borderRadius: 999,
        border: `1px solid ${on ? "#FFFFFF" : "#2C3F72"}`,
        background: on ? "#FFFFFF" : "transparent",
        color: on ? "#0B1446" : "#FFFFFF",
        font: "600 13px inherit",
        cursor: "pointer",
      }}
    >
      {dot && (
        <span
          aria-hidden="true"
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: dot,
          }}
        />
      )}
      {label}
    </button>
  );
}

function Divider() {
  return (
    <span
      aria-hidden="true"
      style={{ width: 1, height: 24, background: "#2C3F72" }}
    />
  );
}

function WorldMap({
  report,
  selected,
  onSelect,
}: {
  report: ConferencesReport;
  selected: Conference | undefined;
  onSelect: (id: string) => void;
}) {
  const placed = report.conferences.filter(
    (c) => c.lat !== null && c.lon !== null,
  );
  return (
    <div
      role="img"
      aria-label={`World map with ${placed.length} conferences in ${report.year}`}
      data-testid="conference-map"
      style={{
        position: "relative",
        width: "100%",
        aspectRatio: "360 / 141",
        background:
          "radial-gradient(ellipse at 50% 35%, #1A2A6C 0%, #0C1446 55%, #070B2A 100%)",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <img
        src={worldMap}
        alt=""
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          pointerEvents: "none",
          filter: "drop-shadow(0 0 12px rgba(70,160,255,0.45))",
        }}
      />
      {OCEANS.map((o, i) => (
        <span
          key={i}
          aria-hidden="true"
          style={{
            position: "absolute",
            left: pct(fx(o.lon)),
            top: pct(fy(o.lat)),
            transform: "translate(-50%, -50%)",
            pointerEvents: "none",
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: "0.28em",
            color: "#7F93D6",
            textAlign: "center",
            whiteSpace: "pre-line",
            lineHeight: 1.5,
          }}
        >
          {o.label}
        </span>
      ))}
      {placed.map((c) => {
        const colour = colourOf(c);
        const on = selected?.id === c.id;
        const at: CSSProperties = {
          position: "absolute",
          left: pct(fx(c.lon!)),
          top: pct(fy(c.lat!)),
        };
        const twice = bookedTwice(c);
        return (
          <span key={c.id}>
            <span
              aria-hidden="true"
              style={{
                ...at,
                pointerEvents: "none",
                width: 34,
                height: 34,
                borderRadius: "50%",
                transform: "translate(-50%, -50%)",
                background: `radial-gradient(circle, ${colour}AA 0%, transparent 70%)`,
              }}
            />
            {report.next_id === c.id && (
              <span
                className="conf-ring"
                aria-hidden="true"
                style={{
                  ...at,
                  pointerEvents: "none",
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  border: "2px solid #FFFFFF",
                  boxSizing: "border-box",
                }}
              />
            )}
            <button
              type="button"
              className="conf-pin"
              data-testid="conference-pin"
              aria-label={`${c.name}, ${c.city ?? ""}, ${formatDay(c.starts_on)} (${priorityLabel(c.priority)}${twice.length ? `, date clash: ${twice.join(", ")} booked twice` : ""})`}
              aria-pressed={on}
              onClick={() => onSelect(c.id)}
              style={{
                ...at,
                transform: "translate(-50%, -50%)",
                width: on ? 16 : 11,
                height: on ? 16 : 11,
                borderRadius: "50%",
                background: "#FFFFFF",
                border: 0,
                padding: 0,
                cursor: "pointer",
                boxShadow: `0 0 0 3px ${colour}, 0 0 14px 5px ${colour}${on ? ", 0 0 0 7px rgba(255,255,255,0.35)" : ""}`,
              }}
            />
            <span
              aria-hidden="true"
              style={{
                ...at,
                pointerEvents: "none",
                transform: "translate(14px, -50%)",
                fontSize: 11,
                fontWeight: 600,
                color: "#FFFFFF",
                background: "rgba(7,11,42,0.72)",
                border: `1px solid ${on ? "#FFFFFF" : twice.length && !c.past ? "#FF8A50" : `${colour}66`}`,
                borderRadius: 6,
                padding: "2px 7px",
                whiteSpace: "nowrap",
              }}
            >
              {c.city}
              {twice.length > 0 && !c.past ? " !" : ""}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function Details({ c }: { c: Conference }) {
  const colour = colourOf(c);
  const registration = c.register_by
    ? `${formatDay(c.register_by)}${c.registration && !/^\d{4}-/.test(c.registration) ? ` (${c.registration})` : ""}`
    : (c.registration ?? "—");
  const rows: [string, string][] = [
    ["Who is going", c.team ?? "—"],
    ["Registration", registration],
    ["Gov support", c.gov_support ?? "—"],
    ["Tags", c.tags.join(", ") || "—"],
    ...(c.booth ? ([["Booth", c.booth]] as [string, string][]) : []),
    ["Why go", c.notes ?? "—"],
  ];
  const twice = bookedTwice(c);
  return (
    <Card
      data-testid="conference-details"
      style={{ borderTop: `4px solid ${colour}` }}
      styles={{ body: { display: "flex", flexDirection: "column", gap: 8 } }}
    >
      <Tag
        style={{
          alignSelf: "flex-start",
          background: colour,
          color: "#0B1446",
          border: 0,
          fontWeight: 700,
        }}
      >
        {priorityLabel(c.priority)}
        {c.past ? " · done" : ""}
      </Tag>
      <Typography.Title level={4} style={{ margin: 0 }}>
        {c.name}
      </Typography.Title>
      <Typography.Text>
        {[c.city, c.country].filter(Boolean).join(", ") ||
          "Location not recorded"}
      </Typography.Text>
      <Typography.Text strong>
        {span(c.starts_on, c.ends_on)}{" "}
        <Typography.Text type="secondary">· {when(c)}</Typography.Text>
      </Typography.Text>
      {c.clashes.length > 0 && (
        <Alert
          type={twice.length ? "warning" : "info"}
          showIcon
          title={
            twice.length
              ? `Date clash: ${twice.join(" and ")} booked twice`
              : "Date clash (different people)"
          }
          description={c.clashes
            .map((k) => `${k.name}, ${span(k.starts_on, k.ends_on)}`)
            .join(" · ")}
        />
      )}
      {c.register_soon && (
        <Alert
          type="warning"
          showIcon
          title={`Registration closes ${formatDay(c.register_by!)}`}
        />
      )}
      <dl
        style={{
          margin: 0,
          display: "grid",
          gridTemplateColumns: "max-content 1fr",
          gap: "6px 12px",
          fontSize: 13,
        }}
      >
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt style={{ color: "#5B6B82" }}>{k}</dt>
            <dd style={{ margin: 0 }}>{v}</dd>
          </div>
        ))}
      </dl>
      <Flex gap={12} wrap>
        {c.website && (
          <a href={c.website} target="_blank" rel="noreferrer">
            Conference website
          </a>
        )}
        {c.source_url && (
          <a href={c.source_url} target="_blank" rel="noreferrer">
            Open in SharePoint
          </a>
        )}
      </Flex>
    </Card>
  );
}

function Clashes({
  groups,
  onPick,
}: {
  groups: ClashGroup[];
  onPick: (name: string) => void;
}) {
  return (
    <Card
      title={`Date clashes (${groups.length})`}
      data-testid="conference-clashes"
      styles={{ body: { display: "flex", flexDirection: "column", gap: 8 } }}
    >
      {groups.length === 0 ? (
        <Typography.Text type="secondary">
          No overlapping dates this year.
        </Typography.Text>
      ) : (
        groups.map((g) => (
          <div
            key={`${g.starts_on}-${g.names.join("|")}`}
            style={{
              border: `1px solid ${g.shared.length ? "#F5C9A8" : "#DDE3EC"}`,
              background: g.shared.length ? "#FFF7ED" : "#F8FAFC",
              borderRadius: 8,
              padding: "8px 10px",
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            <Flex justify="space-between" gap={8} wrap>
              <strong style={{ fontSize: 13 }}>
                {span(g.starts_on, g.ends_on)}
              </strong>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: g.shared.length ? "#9A3412" : "#3D4757",
                }}
              >
                {g.shared.length
                  ? `${g.shared.join(" and ")} booked twice`
                  : "Different people"}
              </span>
            </Flex>
            <Flex gap={6} wrap>
              {g.names.map((n) => (
                <Button
                  key={n}
                  size="small"
                  type="link"
                  style={{ padding: 0, height: "auto" }}
                  onClick={() => onPick(n)}
                >
                  {n}
                </Button>
              ))}
            </Flex>
          </div>
        ))
      )}
    </Card>
  );
}

/** Conferences: where Avion's BD team is going, from their SharePoint list (read-only). Budgets are never read. */
export function ConferencesPage() {
  const { message } = App.useApp();
  const [params, setParams] = useSearchParams();
  const year = params.get("year") ? Number(params.get("year")) : undefined;
  const priority = params.get("priority") ?? undefined;
  const who = params.get("who") ?? undefined;
  const tag = params.get("tag") ?? undefined;
  const picked = params.get("id") ?? undefined;
  const { data, isLoading, isError, error, refetch } = useConferences({
    year,
    priority,
    who,
    tag,
  });
  const refresh = useRefreshConferences();

  const set = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load conferences"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    );
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 12 }} />;

  const selected =
    data.conferences.find((c) => c.id === picked) ??
    data.conferences.find((c) => c.id === data.next_id) ??
    data.conferences[0];
  const exportUrl = conferencesExportUrl({
    year: String(data.year),
    priority,
    who,
    tag,
  });
  const pickByName = (name: string) => {
    const c = data.conferences.find((x) => x.name === name);
    if (c) set({ id: c.id });
    else
      set({
        priority: undefined,
        who: undefined,
        tag: undefined,
        id: undefined,
      });
  };

  return (
    <Flex vertical gap={16}>
      <PageHeader
        title="Where Avion is going"
        subtitle="Conferences the BD team plans to attend, from their SharePoint schedules. Click a pin for the details."
        extra={
          <Flex gap={8} wrap align="center" className="no-print">
            <Tooltip
              title={
                data.source.files?.length
                  ? `Read from: ${data.source.files.join(", ")}`
                  : undefined
              }
            >
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {data.source.mode === "sharepoint"
                  ? `SharePoint · BD conferences · ${data.source.fetched_at ? formatDateTime(data.source.fetched_at) : "not read yet"}`
                  : "Demo data"}
              </Typography.Text>
            </Tooltip>
            <Button
              icon={<SyncOutlined />}
              loading={refresh.isPending}
              onClick={() =>
                refresh.mutate(undefined, {
                  onSuccess: () => void message.success("Conferences synced"),
                  onError: (e) => void message.error(e.message),
                })
              }
            >
              Sync now
            </Button>
            <Button icon={<FileExcelOutlined />} href={exportUrl}>
              Excel
            </Button>
            <Button icon={<FilePdfOutlined />} onClick={() => window.print()}>
              PDF
            </Button>
          </Flex>
        }
      />
      {data.source.mode === "demo" && (
        <Alert
          type="warning"
          showIcon
          title="Demo conferences: the BD team's SharePoint schedules are not connected yet"
          description={`${data.source.reason ?? ""} These conferences are made up and are not Avion's plans.`}
        />
      )}

      <ReportTiles tiles={data.tiles} />

      <section
        aria-label="World map"
        style={{
          background: "#070B2A",
          borderRadius: 16,
          padding: 14,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <Flex
          gap={8}
          wrap
          align="center"
          className="no-print"
          role="group"
          aria-label="Year and priority"
        >
          {data.years.map((y) => (
            <Chip
              key={y}
              on={y === data.year}
              label={String(y)}
              onClick={() => set({ year: String(y), id: undefined })}
            />
          ))}
          <Divider />
          <Chip
            on={!priority}
            label="All"
            onClick={() => set({ priority: undefined, id: undefined })}
          />
          {PRIORITIES.map((p) => (
            <Chip
              key={p}
              on={priority === String(p)}
              label={`Priority ${p}`}
              dot={PRIORITY_COLOUR[p]}
              onClick={() => set({ priority: String(p), id: undefined })}
            />
          ))}
        </Flex>
        {(data.attendees.length > 0 || data.tags.length > 0) && (
          <Flex
            gap={8}
            wrap
            align="center"
            className="no-print"
            role="group"
            aria-label="Who is going and tags"
          >
            {data.attendees.length > 0 && (
              <>
                <span style={{ color: "#C9D5E6", fontSize: 12 }}>Who</span>
                <Chip
                  on={!who}
                  label="Everyone"
                  onClick={() => set({ who: undefined, id: undefined })}
                />
                {data.attendees.map((p) => (
                  <Chip
                    key={p}
                    on={who === p}
                    label={p}
                    onClick={() => set({ who: p, id: undefined })}
                  />
                ))}
              </>
            )}
            {data.tags.length > 0 && (
              <>
                <Divider />
                <span style={{ color: "#C9D5E6", fontSize: 12 }}>Tag</span>
                <Chip
                  on={!tag}
                  label="Any"
                  onClick={() => set({ tag: undefined, id: undefined })}
                />
                {data.tags.map((t) => (
                  <Chip
                    key={t}
                    on={tag === t}
                    label={t}
                    onClick={() => set({ tag: t, id: undefined })}
                  />
                ))}
              </>
            )}
          </Flex>
        )}
        <WorldMap
          report={data}
          selected={selected}
          onSelect={(id) => set({ id })}
        />
        <Flex gap={16} wrap style={{ fontSize: 12, color: "#C9D5E6" }}>
          {[
            ...PRIORITIES.map(
              (p) => [`Priority ${p}`, PRIORITY_COLOUR[p]] as const,
            ),
            ["Already happened", PAST] as const,
          ].map(([label, colour]) => (
            <span
              key={label}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: "#FFFFFF",
                  boxShadow: `0 0 0 3px ${colour}, 0 0 10px 3px ${colour}`,
                }}
              />
              {label}
            </span>
          ))}
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              aria-hidden="true"
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                border: "2px solid #FFFFFF",
                boxSizing: "border-box",
              }}
            />
            Next conference (pulses)
          </span>
          <span>“!” someone is booked twice</span>
          {data.not_on_map > 0 && (
            <span>{data.not_on_map} not on the map (city not known yet)</span>
          )}
        </Flex>
      </section>

      {selected ? (
        <Details c={selected} />
      ) : (
        <Card>
          <Typography.Text type="secondary">
            No conferences in this selection.
          </Typography.Text>
        </Card>
      )}

      <MoreDetail
        summary={`More detail: date clashes (${data.clash_groups.length}) and all conferences in ${data.year} (${data.conferences.length})`}
      >
        <Flex gap={14} wrap align="flex-start">
          <Flex vertical gap={14} style={{ flex: "1 1 320px", minWidth: 0 }}>
            <Clashes groups={data.clash_groups} onPick={pickByName} />
          </Flex>
          <Card
            title={`All conferences in ${data.year} (${data.conferences.length})`}
            style={{ flex: "2 1 560px", minWidth: 0 }}
          >
            <Table<Conference>
              size="small"
              rowKey="id"
              dataSource={data.conferences}
              pagination={false}
              scroll={{ x: 820 }}
              locale={{ emptyText: "No conferences in this selection." }}
              onRow={(c) =>
                ({
                  "data-testid": "conference-row",
                  onClick: () => set({ id: c.id }),
                  style: {
                    cursor: "pointer",
                    background: c.id === selected?.id ? "#EEF3FB" : undefined,
                  },
                }) as HTMLAttributes<HTMLElement>
              }
              columns={[
                {
                  title: "Dates",
                  key: "dates",
                  width: 160,
                  render: (_, c) => (
                    <strong>{span(c.starts_on, c.ends_on)}</strong>
                  ),
                },
                {
                  title: "Conference",
                  key: "name",
                  render: (_, c) => (
                    <Flex vertical gap={2}>
                      <span>{c.name}</span>
                      {c.tags.length > 0 && (
                        <Flex gap={4} wrap>
                          {c.tags.map((t) => (
                            <Tag key={t} color="blue" style={{ margin: 0 }}>
                              {t}
                            </Tag>
                          ))}
                        </Flex>
                      )}
                    </Flex>
                  ),
                },
                {
                  title: "Where",
                  key: "where",
                  width: 160,
                  render: (_, c) =>
                    [c.city, c.country].filter(Boolean).join(", ") || "—",
                },
                {
                  title: "Priority",
                  key: "priority",
                  width: 110,
                  render: (_, c) => (
                    <span
                      style={{ display: "flex", alignItems: "center", gap: 6 }}
                    >
                      <span
                        aria-hidden="true"
                        style={{
                          width: 10,
                          height: 10,
                          borderRadius: "50%",
                          background: colourOf(c),
                        }}
                      />
                      {c.priority ? c.priority : "—"}
                    </span>
                  ),
                },
                {
                  title: "Who",
                  key: "who",
                  width: 90,
                  render: (_, c) => c.team ?? "—",
                },
                {
                  title: "When",
                  key: "when",
                  width: 140,
                  render: (_, c) => (
                    <Flex vertical gap={0}>
                      <span>{when(c)}</span>
                      {c.register_soon && (
                        <Typography.Text
                          type="warning"
                          style={{ fontSize: 12 }}
                        >
                          Register soon
                        </Typography.Text>
                      )}
                      {bookedTwice(c).length > 0 && !c.past && (
                        <Typography.Text type="danger" style={{ fontSize: 12 }}>
                          Clash: {bookedTwice(c).join(", ")} booked twice
                        </Typography.Text>
                      )}
                    </Flex>
                  ),
                },
              ]}
            />
          </Card>
        </Flex>
      </MoreDetail>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.source} Map outlines: Natural Earth (public domain).
      </Typography.Text>
    </Flex>
  );
}
