import type {
  ClassificationLabel,
  CreateLabelPayload,
  UpdateLabelPayload,
} from "../types/classification";
import { useCrudResource } from "./useCrudResource";

export function useClassificationLabels() {
  const { items: labels, loading, error, create, update, remove } =
    useCrudResource<ClassificationLabel, CreateLabelPayload, UpdateLabelPayload>(
      "/api/classification/labels",
    );

  return {
    labels,
    loading,
    error,
    createLabel: create,
    updateLabel: update,
    deleteLabel: remove,
  };
}
