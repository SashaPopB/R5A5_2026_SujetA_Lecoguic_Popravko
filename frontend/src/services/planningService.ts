import { requete } from "../api/client.ts";
import type { PlanningDto } from "../api/dto.ts";
import { versPlanning } from "../api/mappers.ts";
import type { Planning } from "../models/index.ts";

export async function chargerPlanning(date: string, signal?: AbortSignal): Promise<Planning> {
  const dto = await requete<PlanningDto>(`/planning?${new URLSearchParams({ date })}`, { signal });
  return versPlanning(dto);
}
