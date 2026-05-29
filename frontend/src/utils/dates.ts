const ISO_WITHOUT_ZONE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

export function parseApiDate(value: string): Date {
  return new Date(ISO_WITHOUT_ZONE.test(value) ? `${value}Z` : value);
}

export function utcDateTimeLabel(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZoneName: "short",
  }).format(parseApiDate(iso));
}

export function utcDateLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
  }).format(parseApiDate(iso));
}

export function utcMonthYearLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    month: "short",
    year: "numeric",
  }).format(parseApiDate(iso));
}

export function utcYearLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    year: "numeric",
  }).format(parseApiDate(iso));
}

export function utcTimeLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parseApiDate(iso));
}
