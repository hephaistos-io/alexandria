export interface GraphNode {
  qid: string;
  name: string;
  entity_type: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation_type: string;
  display_strength: number;
  base_strength: number;
  last_seen: string;
  first_seen: string;
  article_count: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface RelationType {
  id: number;
  name: string;
  description: string;
  color: string;
  directed: boolean;
  enabled: boolean;
  created_at: string;
}

export interface CreateRelationTypePayload {
  name: string;
  description: string;
  color: string;
  directed: boolean;
}

export interface UpdateRelationTypePayload {
  description?: string;
  color?: string;
  directed?: boolean;
  enabled?: boolean;
}
