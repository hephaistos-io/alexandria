export interface ClassificationLabel {
  id: number;
  name: string;
  description: string;
  color: string;
  enabled: boolean;
  created_at: string;
}

export interface CreateLabelPayload {
  name: string;
  description: string;
  color: string;
}

export interface UpdateLabelPayload {
  description?: string;
  color?: string;
  enabled?: boolean;
}
