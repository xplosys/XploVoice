// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type Appointment, type Availability, type Calendar, type Holiday } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Select } from "@/components/ui";
import { addHolidayAction, appointmentAction, bookAction, removeHolidayAction, saveCalendarAction } from "../workflow-actions";

export const metadata = { title: "Appointments · XploVoice" };

const DAYS = [["mon", "Mon"], ["tue", "Tue"], ["wed", "Wed"], ["thu", "Thu"], ["fri", "Fri"], ["sat", "Sat"], ["sun", "Sun"]] as const;
const TZ = ["Asia/Kolkata", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "UTC"];
const TONE = { booked: "green", cancelled: "red", completed: "slate", no_show: "amber" } as const;

function CalendarForm({ c }: { c?: Calendar }) {
  return (
    <ActionForm action={saveCalendarAction} submit={c ? "Save calendar" : "Create calendar"}>
      {c && <input type="hidden" name="id" value={c.id} />}
      <div className="grid gap-3 sm:grid-cols-3">
        <div><Label htmlFor={`n${c?.id}`}>Name</Label><Input id={`n${c?.id}`} name="name" required maxLength={120} defaultValue={c?.name ?? "Main calendar"} /></div>
        <div><Label htmlFor={`tz${c?.id}`}>Time zone</Label><Select id={`tz${c?.id}`} name="timezone" defaultValue={c?.timezone ?? "Asia/Kolkata"}>{TZ.map((z) => <option key={z}>{z}</option>)}</Select></div>
        <div><Label htmlFor={`s${c?.id}`}>Appointment length (minutes)</Label><Input id={`s${c?.id}`} name="slot_minutes" type="number" min={5} max={240} defaultValue={c?.slot_minutes ?? 30} /></div>
        <div><Label htmlFor={`m${c?.id}`}>Minimum notice (minutes)</Label><Input id={`m${c?.id}`} name="min_notice_minutes" type="number" min={0} max={10080} defaultValue={c?.min_notice_minutes ?? 60} /></div>
        <div><Label htmlFor={`h${c?.id}`}>Book up to (days ahead)</Label><Input id={`h${c?.id}`} name="horizon_days" type="number" min={1} max={180} defaultValue={c?.horizon_days ?? 30} /></div>
        {c && <div><Label htmlFor={`st${c.id}`}>Status</Label><Select id={`st${c.id}`} name="status" defaultValue={c.status}><option value="active">Active</option><option value="archived">Archived</option></Select></div>}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {DAYS.map(([d, label]) => {
          const w = c?.weekly[d]?.[0];
          const on = c ? !!w : !["sat", "sun"].includes(d);
          return (
            <div key={d} className="flex items-center gap-2 text-sm">
              <label className="flex w-16 items-center gap-1"><input type="checkbox" name={`${d}_on`} defaultChecked={on} /> {label}</label>
              <Input aria-label={`${label} opens`} name={`${d}_start`} type="time" defaultValue={w?.start ?? "09:00"} className="w-28 py-1" />
              <span>to</span>
              <Input aria-label={`${label} closes`} name={`${d}_end`} type="time" defaultValue={w?.end ?? "18:00"} className="w-28 py-1" />
            </div>
          );
        })}
      </div>
    </ActionForm>
  );
}

export default async function AppointmentsPage({ searchParams }: { searchParams: Promise<{ cal?: string; day?: string }> }) {
  const me = await getMe();
  if (!can(me, "workflows:read")) redirect("/app");
  const sp = await searchParams;
  const [cals, holidays, upcoming, past] = await Promise.all([
    api<Calendar[]>("/v1/booking-calendars"), api<Holiday[]>("/v1/holidays"),
    api<Appointment[]>("/v1/appointments?upcoming=true&limit=100"), api<Appointment[]>("/v1/appointments?limit=30"),
  ]);
  const manage = can(me, "workflows:manage");
  const active = cals.filter((c) => c.status === "active");
  const cal = active.find((c) => c.id === sp.cal) ?? active[0];
  const avail = cal ? await api<Availability>(`/v1/booking-calendars/${cal.id}/availability${sp.day ? `?day=${encodeURIComponent(sp.day)}` : ""}`).catch(() => null) : null;
  const calName = new Map(cals.map((c) => [c.id, c.name]));
  const earlier = past.filter((a) => new Date(a.starts_at) < new Date());
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Appointments</h1>
        <p className="text-sm text-slate-600">Bookings made by your agents on calls and by your team. Agents book only free times in the calendar you give them.</p>
      </div>

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">Upcoming</h2>
        {upcoming.length === 0 ? <p className="p-6 text-sm text-slate-600">Nothing booked.</p> : (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {upcoming.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
                <div>
                  <p className="font-medium">{a.local_start.replace("T", " ")} <span className="text-xs font-normal text-slate-500">({a.timezone}) · {a.calendar}</span></p>
                  <p className="text-slate-600">{a.customer_name}{a.customer_phone ? ` · ${a.customer_phone}` : ""} · <span className="font-mono text-xs">{a.reference}</span>
                    {" "}· from {a.source}{a.call_id && <> (<Link className="underline" href={`/app/calls/${a.call_id}`}>record</Link>)</>}</p>
                  {a.notes && <p className="text-xs text-slate-500">{a.notes}</p>}
                </div>
                <div className="flex items-center gap-2"><Badge tone={TONE[a.status]}>{a.status.replace("_", " ")}</Badge>
                  {manage && a.status === "booked" && (<>
                    <ActionForm action={appointmentAction} submit="Done" variant="ghost" className=""><input type="hidden" name="id" value={a.id} /><input type="hidden" name="op" value="completed" /></ActionForm>
                    <ActionForm action={appointmentAction} submit="Cancel" variant="ghost" className=""><input type="hidden" name="id" value={a.id} /><input type="hidden" name="op" value="cancel" /></ActionForm>
                  </>)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {cal && avail && (
        <Card>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <h2 className="font-medium">Free times{avail.date ? ` on ${avail.date}` : ""}</h2>
            <form className="flex items-end gap-2" action="/app/appointments">
              <div><Label htmlFor="cal">Calendar</Label><Select id="cal" name="cal" defaultValue={cal.id}>{active.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></div>
              <div><Label htmlFor="day">Day</Label><Input id="day" name="day" type="date" defaultValue={sp.day ?? avail.date} /></div>
              <button className="rounded-md border border-slate-300 px-3 py-2 text-sm">Show</button>
            </form>
          </div>
          {avail.asked_date_note && <p className="mb-2 text-sm text-amber-800">{avail.asked_date_note}</p>}
          {avail.slots.length === 0 ? <p className="text-sm text-slate-600">{avail.note ?? "No free times."}</p> : (
            <div className="flex flex-wrap gap-2">{avail.slots.map((s) => <span key={s.start} className="rounded-md bg-slate-100 px-2 py-1 text-xs">{s.start.slice(11)}</span>)}</div>
          )}
          {manage && avail.slots.length > 0 && (
            <div className="mt-4 border-t border-slate-200 pt-4">
              <h3 className="mb-2 text-sm font-medium">Book by hand</h3>
              <ActionForm action={bookAction} submit="Book">
                <input type="hidden" name="calendar_id" value={cal.id} />
                <div className="grid gap-3 sm:grid-cols-3">
                  <div><Label htmlFor="start">Time</Label><Select id="start" name="start">{avail.slots.map((s) => <option key={s.start} value={s.start}>{s.say}</option>)}</Select></div>
                  <div><Label htmlFor="cn">Name</Label><Input id="cn" name="customer_name" required maxLength={120} /></div>
                  <div><Label htmlFor="cp">Phone (optional)</Label><Input id="cp" name="customer_phone" maxLength={30} /></div>
                </div>
                <div><Label htmlFor="notes">Notes (optional)</Label><Input id="notes" name="notes" maxLength={1000} /></div>
              </ActionForm>
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card>
          <h2 className="mb-3 font-medium">Booking calendars</h2>
          <div className="space-y-6">
            {cals.map((c) => (
              <details key={c.id} className="rounded-md border border-slate-200 p-3">
                <summary className="cursor-pointer text-sm font-medium">{c.name} <span className="font-normal text-slate-500">· {c.slot_minutes} min · {c.timezone}</span> {c.status !== "active" && <Badge tone="red">archived</Badge>}</summary>
                <div className="mt-3">{manage ? <CalendarForm c={c} /> : <p className="text-sm text-slate-600">Read only.</p>}</div>
              </details>
            ))}
            {manage && <details open={cals.length === 0} className="rounded-md border border-dashed border-slate-300 p-3">
              <summary className="cursor-pointer text-sm font-medium">New calendar</summary><div className="mt-3"><CalendarForm /></div></details>}
          </div>
        </Card>
        <Card>
          <h2 className="mb-1 font-medium">Holidays</h2>
          <p className="mb-3 text-xs text-slate-500">An organisation-wide holiday closes every calendar and every agent&apos;s business hours that day.</p>
          <ul className="mb-4 space-y-1 text-sm">
            {holidays.length === 0 && <li className="text-slate-600">None.</li>}
            {holidays.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-2">
                <span>{h.day} · {h.name} <span className="text-xs text-slate-500">{h.calendar_id ? calName.get(h.calendar_id) : "everything"}</span></span>
                {manage && <ActionForm action={removeHolidayAction} submit="×" variant="ghost" className=""><input type="hidden" name="id" value={h.id} /></ActionForm>}
              </li>
            ))}
          </ul>
          {manage && <ActionForm action={addHolidayAction} submit="Add holiday">
            <div><Label htmlFor="hday">Day</Label><Input id="hday" name="day" type="date" required /></div>
            <div><Label htmlFor="hname">Name</Label><Input id="hname" name="name" required maxLength={120} placeholder="Diwali" /></div>
            <div><Label htmlFor="hcal">Applies to</Label><Select id="hcal" name="calendar_id"><option value="">The whole organisation</option>{cals.map((c) => <option key={c.id} value={c.id}>{c.name} only</option>)}</Select></div>
          </ActionForm>}
        </Card>
      </div>

      {earlier.length > 0 && (
        <Card><h2 className="mb-2 font-medium">Recent past</h2>
          <ul className="space-y-1 text-sm">{earlier.slice(0, 15).map((a) => <li key={a.id}>{a.local_start.replace("T", " ")} · {a.customer_name} · <Badge tone={TONE[a.status]}>{a.status.replace("_", " ")}</Badge></li>)}</ul>
        </Card>
      )}
    </div>
  );
}
