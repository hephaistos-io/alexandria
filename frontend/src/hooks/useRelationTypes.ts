import type {
  RelationType,
  CreateRelationTypePayload,
  UpdateRelationTypePayload,
} from "../types/graph";
import { useCrudResource } from "./useCrudResource";

export function useRelationTypes() {
  const { items: relationTypes, loading, error, create, update, remove } =
    useCrudResource<RelationType, CreateRelationTypePayload, UpdateRelationTypePayload>(
      "/api/graph/relation-types",
    );

  return {
    relationTypes,
    loading,
    error,
    createRelationType: create,
    updateRelationType: update,
    deleteRelationType: remove,
  };
}
