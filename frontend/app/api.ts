export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function api<T>(path: string, body?: unknown): Promise<T> {
 const response = await fetch(API + path, {
  credentials: 'include',
  ...(body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}),
 }).catch(() => {throw new Error(`Cannot reach the OwnIt API at ${API}. Start the FastAPI backend and check your API URL.`);});
 const data = await response.json().catch(() => null);
 if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : response.status === 422 ? 'Invalid input. Check the pull-request URL and required fields.' : `The backend returned an error (${response.status}). Check its terminal and retry.`);
 if (data === null) throw new Error('The backend returned an unexpected response. Check the API URL.');
 return data;
}
