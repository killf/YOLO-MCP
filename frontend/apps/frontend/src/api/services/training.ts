import type { MetaData } from '../types';
import request from '../request';

export type TrainingStatus = 'PENDING' | 'RUNNING' | 'PAUSING' | 'PAUSED' | 'SUCCEEDED' | 'FAILED' | 'INTERRUPTED';

export interface TrainingParameters {
  algorithm?: 'yolo26_detect';
  initial_model: string;
  epochs: number;
  imgsz: number;
  batch: number;
  lr0?: number | null;
  augmentation?: boolean;
  training_scope?: 'full' | 'head' | 'head_then_full';
  unfreeze_steps?: number;
  extra_params?: Record<string, unknown>;
}

export interface TrainingParameterDescription {
  name: string;
  default: unknown;
  description: string;
}

export function getTrainingParameters(projectId: number) {
  return request.get<never, { data: TrainingParameterDescription[] }>(
    `/v1/projects/${projectId}/training-runs/parameters`,
  );
}

export interface TrainingRun {
  id: number;
  project_id: number;
  status: TrainingStatus;
  initial_model: string;
  parameters: TrainingParameters;
  model_name: string | null;
  model_available: boolean;
  log_available: boolean;
  pause_available: boolean;
  resume_available: boolean;
  run_id: string | null;
  metrics: Record<string, number>;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export function startTraining(projectId: number, parameters: TrainingParameters) {
  return request.post<never, { data: TrainingRun }>(`/v1/projects/${projectId}/training-runs`, parameters);
}

export function pauseTraining(projectId: number, runId: number) {
  return request.post<never, { data: TrainingRun }>(`/v1/projects/${projectId}/training-runs/${runId}/pause`);
}

export function resumeTraining(projectId: number, runId: number) {
  return request.post<never, { data: TrainingRun }>(`/v1/projects/${projectId}/training-runs/${runId}/resume`);
}

export function getTrainingRuns(projectId: number, page = 0, size = 10) {
  return request.get<never, { data: TrainingRun[]; meta_data: MetaData }>(`/v1/projects/${projectId}/training-runs`, {
    params: { page, size },
  });
}

export function getTrainingLog(projectId: number, runId: number) {
  return request.get<never, string>(`/v1/projects/${projectId}/training-runs/${runId}/log`, { responseType: 'text' });
}

export function clearTrainingLogs(projectId: number, runId: number) {
  return request.delete(`/v1/projects/${projectId}/training-runs/${runId}/log`);
}

export function deleteTrainingRun(projectId: number, runId: number) {
  return request.delete(`/v1/projects/${projectId}/training-runs/${runId}`);
}

export async function downloadModel(projectId: number, name: string) {
  const blob = await request.get<never, Blob>(`/v1/projects/${projectId}/models/${encodeURIComponent(name)}`, {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
