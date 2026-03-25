import type {
  EntityRoleType,
  CreateRoleTypePayload,
  UpdateRoleTypePayload,
} from "../types/attribution";
import { useCrudResource } from "./useCrudResource";

export function useEntityRoleTypes() {
  const { items: roleTypes, loading, error, create, update, remove } =
    useCrudResource<EntityRoleType, CreateRoleTypePayload, UpdateRoleTypePayload>(
      "/api/attribution/role-types",
    );

  return {
    roleTypes,
    loading,
    error,
    createRoleType: create,
    updateRoleType: update,
    deleteRoleType: remove,
  };
}
