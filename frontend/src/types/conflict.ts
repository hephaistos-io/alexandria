export interface ConflictEvent {
  id: number;
  source_id: string;
  source: string;
  title: string;
  description: string | null;
  latitude: number;
  longitude: number;
  event_date: string | null;
  place_desc: string;
  links: string[];
  created_at: string;
}
