const DB_NAME = "aapad-snehi-offline";
const STORE = "citizen-reports";

type QueuedReport = {
  id: string;
  createdAt: string;
  fields: Array<[string, string | Blob]>;
};

export function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 2);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        request.result.createObjectStore(STORE, { keyPath: "id" });
      }
      if (!request.result.objectStoreNames.contains("flood-drafts")) {
        request.result.createObjectStore("flood-drafts", { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function asPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function queueCitizenReport(form: FormData): Promise<string> {
  const id = `offline-${crypto.randomUUID()}`;
  const fields = Array.from(form.entries()).map(([key, value]) => [key, value] as [string, string | Blob]);
  const db = await openDatabase();
  const transaction = db.transaction(STORE, "readwrite");
  transaction.objectStore(STORE).put({ id, createdAt: new Date().toISOString(), fields });
  await new Promise<void>((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  db.close();
  return id;
}

export async function flushCitizenReports(
  submit: (form: FormData) => Promise<unknown>,
): Promise<number> {
  const db = await openDatabase();
  const queued = await asPromise(
    db.transaction(STORE, "readonly").objectStore(STORE).getAll() as IDBRequest<QueuedReport[]>,
  );
  let sent = 0;
  for (const report of queued) {
    const form = new FormData();
    for (const [key, value] of report.fields) form.append(key, value);
    try {
      await submit(form);
      const transaction = db.transaction(STORE, "readwrite");
      transaction.objectStore(STORE).delete(report.id);
      await new Promise<void>((resolve) => {
        transaction.oncomplete = () => resolve();
      });
      sent += 1;
    } catch {
      break;
    }
  }
  db.close();
  return sent;
}
