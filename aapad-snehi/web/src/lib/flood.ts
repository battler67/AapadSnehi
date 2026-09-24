import { API_BASE } from "./api";
import { openDatabase } from "./offline-queue";

export type Location = {
  latitude: number | null;
  longitude: number | null;
  source: string;
  accuracy: number | null;
  confirmed: boolean;
  precision: string;
};
export type Address = Record<
  | "state"
  | "city"
  | "locality"
  | "ward"
  | "street"
  | "street_number"
  | "building"
  | "door"
  | "floor"
  | "landmark"
  | "directions",
  string
>;
export type Submission = {
  idempotency_key: string;
  reporter_token: string;
  kind: string;
  update_incident_id: number | null;
  location: Location;
  address: Address;
  observed_at: string | null;
  time_quality: string;
  water_level: string;
  trend: string;
  access: string;
  description: string;
  people: number | null;
  count_quality: string;
  position: string;
  assistance: string[];
  contact: string;
  reporter_present: boolean;
};
export type PhotoReview = {
  status: string;
  message: string;
  caption?: string;
  evidence?: string;
};
export type Receipt = {
  media?: { id: string; review: PhotoReview }[];
  reference: string;
  reportId: number;
  incidentId: number;
  receivedAt: string;
  reviewStatus: string;
  locationStatus: string;
  mediaCount: number;
  message: string;
};
export type Photo = {
  review?: PhotoReview;
  id: string;
  file: Blob;
  name: string;
  attached?: string;
  error?: string;
};
export type Draft = {
  id: string;
  payload: Submission;
  photos: Photo[];
  state: "draft" | "queued" | "received";
  receipt?: Receipt;
};
export type Task = {
  id: string;
  incidentId: number;
  state: string;
  version: number;
  teamId: string | null;
  outcome: string;
  assisted: number | null;
  remaining: string;
  updatedAt: string;
};
export type Report = Omit<Submission, "reporter_token" | "idempotency_key"> & {
  id: number;
  reference: string;
  receivedAt: string;
  locationStatus: string;
  media: { id: string; public: boolean; review?: PhotoReview }[];
};
export type Incident = {
  id: number;
  version: number;
  demo: boolean;
  status: string;
  verification: string;
  urgency: string;
  urgencyReason?: string;
  point: [number, number] | null;
  precision: string;
  locationStatus: string;
  city: string;
  locality: string;
  ward: string;
  street: string;
  types: string[];
  reportCount: number;
  lastObservation: string | null;
  stale: boolean;
  conflict: boolean;
  reviewNeeded: boolean;
  waterLevel: string;
  trend: string;
  access: string;
  assignmentStates: string[];
  conditionBasis: string;
  address?: Address;
  location?: Location;
  reportedPeople?: number | null;
  confirmedPeople?: number | null;
  countQuality?: string;
  canonicalReportId?: number | null;
  tasks?: Task[];
  reports?: Report[];
  places?: Record<string, string>;
  timeline?: {
    id: number;
    actor: string;
    role: string;
    action: string;
    at: string;
    details: unknown;
  }[];
};
export type Listing = {
  items: Incident[];
  total: number;
  summary: Record<string, number | string | null>;
  definitions: Record<string, string>;
  groups: {
    id: string;
    label: string;
    incidentIds: number[];
    summary: Record<string, number | string | null>;
  }[];
};

export async function floodRequest<T>(
  path: string,
  token = "",
  body?: unknown,
  method = "GET",
  reporter = "",
): Promise<T> {
  const response = await fetch(`${API_BASE}/api/flood${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(reporter ? { "X-Reporter-Token": reporter } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(20000),
    cache: "no-store",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail || `Request failed (${response.status})`),
    );
  }
  return response.json();
}

export function newDraft(): Draft {
  return {
    id: "current",
    state: "draft",
    photos: [],
    payload: {
      idempotency_key: crypto.randomUUID(),
      reporter_token: crypto.randomUUID() + crypto.randomUUID(),
      kind: "rescue",
      update_incident_id: null,
      location: {
        latitude: null,
        longitude: null,
        source: "text",
        accuracy: null,
        confirmed: false,
        precision: "unknown",
      },
      address: {
        state: "",
        city: "",
        locality: "",
        ward: "",
        street: "",
        street_number: "",
        building: "",
        door: "",
        floor: "",
        landmark: "",
        directions: "",
      },
      observed_at: null,
      time_quality: "unknown",
      water_level: "unknown",
      trend: "unknown",
      access: "unknown",
      description: "",
      people: null,
      count_quality: "unknown",
      position: "",
      assistance: [],
      contact: "",
      reporter_present: true,
    },
  };
}

export async function draftStore(
  action: "get" | "put" | "delete",
  draft?: Draft,
): Promise<Draft | undefined> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(
      "flood-drafts",
      action === "get" ? "readonly" : "readwrite",
    );
    const store = tx.objectStore("flood-drafts");
    const request =
      action === "get"
        ? store.get("current")
        : action === "put"
          ? store.put(draft)
          : store.delete("current");
    let result: Draft | undefined;
    request.onsuccess = () => {
      if (action === "get") result = request.result;
    };
    tx.oncomplete = () => {
      db.close();
      resolve(result);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
    tx.onabort = () => {
      db.close();
      reject(tx.error);
    };
  });
}

export async function compressPhoto(file: File): Promise<Blob> {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type))
    throw new Error("Choose a JPEG, PNG or WebP photo");
  if (file.size > 8 * 1024 * 1024)
    throw new Error("Choose a photo smaller than 8 MB");
  const bitmap = await createImageBitmap(file);
  try {
    if (bitmap.width * bitmap.height > 20000000)
      throw new Error("Photo dimensions exceed 20 megapixels");
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas
      .getContext("2d")!
      .drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (blob) =>
          blob ? resolve(blob) : reject(new Error("Could not prepare photo")),
        "image/jpeg",
        0.85,
      ),
    );
  } finally {
    bitmap.close();
  }
}

export function uploadPhoto(
  reportId: number,
  photo: Photo,
  reporter: string,
  progress: (percent: number) => void,
): Promise<{ id: string; review: PhotoReview }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/flood/reports/${reportId}/media`);
    xhr.setRequestHeader("X-Reporter-Token", reporter);
    xhr.timeout = 60000;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) progress(Math.round((100 * e.loaded) / e.total));
    };
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else
          reject(
            new Error(
              typeof data.detail === "string"
                ? data.detail
                : "Photo upload failed",
            ),
          );
      } catch {
        reject(new Error("Invalid upload response"));
      }
    };
    xhr.onerror = xhr.ontimeout = () =>
      reject(
        new Error(
          "Upload interrupted; text report is received. Retry this photo.",
        ),
      );
    const form = new FormData();
    form.append("image", photo.file, "photo.jpg");
    xhr.send(form);
  });
}
