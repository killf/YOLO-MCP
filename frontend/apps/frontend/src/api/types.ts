import type { AnnotationData } from '@yolo-mcp/image';
import type { EnumerableAttribute, ILabel, TextAttribute } from '@yolo-mcp/interface';

import type { TrainingParameters } from './services/training';

export type DatasetSplit = 'train' | 'test';

export interface AttachmentDeleteCommand {
  /** Attachment Ids description: attachment file id */
  attachment_ids: number[];
}

export interface AttachmentResponse {
  /** Id description: upload file id */
  id?: number;
  filename?: string;
  /** Url description: upload file url */
  url?: string;
  thumbnail_url?: string | null;
}

export interface GetUsersApiV1UsersGetParams {
  page?: number;
  size?: number;
  username?: string;
}

export interface UserResponse {
  is_admin?: boolean;
  is_active?: boolean;
  /** Id */
  id?: number;
  /** Username */
  username?: string;
}

export interface BasicConfigCommand {
  /** Name description: project name */
  name: string;
  /** Description description: project description */
  description?: string;
  /** Tips description: project tips */
  tips?: string;
}

export interface BodyCreateApiV1ProjectsProjectIdAttachmentsPost {
  /** File */
  file: string;
}

export interface CommonDataResp {
  /** Ok */
  ok: boolean;
}

export interface CreateApiV1ProjectsProjectIdAttachmentsPostParams {
  project_id: number;
}

export interface CreateApiV1ProjectsProjectIdSamplesPostParams {
  project_id: number;
}

export interface SampleData {
  id?: number;
  state?: SampleState;
  result: string;
}

export interface CreateSampleCommand {
  /** Data description: sample data, include filename, file url, or result */
  data?: SampleData;
}

export interface CreateSampleResponse {
  /** Ids description: attachment ids */
  ids?: number[];
}

export interface DeleteApiV1ProjectsProjectIdAttachmentsDeleteParams {
  project_id: number;
}

export interface DeleteApiV1ProjectsProjectIdDeleteParams {
  project_id: number;
}

export interface DeletePreAnnotationFileParams {
  project_id: number;
  file_id: number;
}

export interface DeleteSampleCommand {
  /** Sample Ids description: attachment file id */
  sample_ids: number[];
}

export interface DownloadAttachmentApiV1ProjectsAttachmentFilePathGetParams {
  file_path: string;
}

export interface AutoLabelResponse {
  status: string;
  project_id: number;
  sample_id: number;
  media_type: MediaType;
  provider: string;
  model?: string | null;
  latency_ms?: number | null;
  pre_annotation_id?: number | null;
  warning_message?: string | null;
}

export interface AutoLabelJobResponse {
  algorithm?: 'yolo' | 'florence2' | 'grounding_dino_sam' | 'sam3';
  model_name: string;
  id: number;
  project_id: number;
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  sample_count: number;
  processed_count: number;
  success_count: number;
  failed_count: number;
  error_message?: string | null;
  created_at?: string | null;
}

export interface GetApiV1ProjectsProjectIdGetParams {
  project_id: number;
}

export interface GetApiV1ProjectsProjectIdSamplesSampleIdGetParams {
  project_id: number;
  sample_id: number;
}

export interface GetPreApiV1ProjectsProjectIdSamplesSampleIdPreGetParams {
  project_id: number;
  sample_id: number;
}

export interface HTTPValidationError {
  /** Detail */
  detail?: ValidationError[];
}

export interface ListByApiV1ProjectsGetParams {
  page?: number;
  size?: number;
}

export interface ListByApiV1ProjectsProjectIdSamplesGetParams {
  project_id: number;
  split?: DatasetSplit;
  state?: SampleState;
  after?: number;
  before?: number;
  page?: number;
  size?: number;
  sort?: string;
}

export interface LoginCommand {
  /** Username */
  username: string;
  /** Password */
  password: string;
}

export interface LoginResponse {
  /** Token description: user credential */
  token: string;
}

export interface LogoutResponse {
  /** Msg */
  msg: string;
}

export enum MediaType {
  IMAGE = 'IMAGE',
  VIDEO = 'VIDEO',
  AUDIO = 'AUDIO',
  // TODO: 后续支持
  // POINT_CLOUD = 'POINT_CLOUD',
}

export interface MetaData {
  /** Total */
  total: number;
  /** Page */
  page?: number;
  /** Size */
  size: number;
}

export interface OkRespAttachmentResponse {
  data: AttachmentResponse;
}

export interface OkRespCommonDataResp {
  data: CommonDataResp;
}

export interface OkRespCreateSampleResponse {
  data: CreateSampleResponse;
}

export interface OkRespLoginResponse {
  data: LoginResponse;
}

export interface OkRespUserInfo {
  data: SignupResponse;
}

export interface OkRespLogoutResponse {
  data: LogoutResponse;
}

export interface OkRespSampleResponse {
  data: SampleResponse;
}

export interface OkRespAutoLabelResponse {
  data: AutoLabelResponse;
}

export interface OkRespSignupResponse {
  data: SignupResponse;
}

export interface OkRespProjectResponse {
  data: ProjectResponse;
}

export interface OkRespProjectResponseWithStatics {
  data: ProjectResponseWithStatics;
}

export interface PatchSampleCommand {
  /** 训练集或测试集。 */
  split?: DatasetSplit;
  /** Data description: sample data, include filename, file url, or result */
  data?: SampleData;
  /** Annotated Count description: annotate result count */
  annotated_count?: number;
  /** description: sample file state, must be 'SKIPPED', 'NEW', or None */
  state?: SampleState;
}

export interface SampleResponse {
  /** 训练集或测试集。 */
  split?: DatasetSplit;
  /** Id description: annotation id */
  id?: number;
  inner_id: number;
  is_pre_annotated: boolean;

  /** State description: sample file state, NEW is has not start yet, DONE is completed, SKIPPED is skipped */
  state?: SampleState;
  /** Data description: sample data, include filename, file url, or result */
  data?: SampleData;
  file: {
    id: number;
    url: string;
    filename: string;
    thumbnail_url?: string | null;
  };
  /** Annotated Count description: annotate result count */
  annotated_count?: number;
  /** Created At description: project created at time */
  created_at?: string;
  /** Created By description: project created by */
  created_by?: UserResp;
  /** Updated At description: project updated at time */
  updated_at?: string;
  /** Updated By description: project updated by */
  updated_by?: UserResp;
}

export interface PreAnnotationResponse {
  /** Id description: annotation id */
  id?: number;
  /** Data description: sample data, include filename, file url, or result */
  data?: PreAnnotationType[];
  file?: {
    id: string;
    url: string;
    filename: string;
    thumbnail_url?: string | null;
  } | null;
  /** Created At description: project created at time */
  created_at?: string;
  /** Created By description: project created by */
  created_by?: UserResp;
  /** Updated At description: project updated at time */
  updated_at?: string;
  /** Updated By description: project updated by */
  updated_by?: UserResp;
}

export interface SampleListResponse {
  meta_data?: MetaData;
  /** Data */
  data: SampleResponse[];
}

export interface AttachmentListResponse {
  meta_data?: MetaData;
  /** Data */
  data: AttachmentResponse[];
}

export interface PreAnnotationListResponse {
  meta_data?: MetaData;
  /** Data */
  data: PreAnnotationResponse[];
}

export interface OkResponse<T> {
  data: T;
}

export interface ListResponseWithMeta<T> {
  meta_data?: MetaData;
  data: T[];
}

export enum SampleState {
  NEW = 'NEW',
  SKIPPED = 'SKIPPED',
  DONE = 'DONE',
}

export interface SignupCommand {
  /** Username */
  username: string;
  /** Password */
  password: string;
}

export interface SignupResponse {
  /** Id */
  id: number;
  /** Username */
  username: string;
}

export interface ProjectResponse {
  ai_algorithm?: 'yolo' | 'florence2' | 'grounding_dino_sam' | 'sam3';
  training_config?: TrainingParameters | null;
  /** 自动标注的权重文件名或官方模型 ID。 */
  ai_model_name?: string | null;
  /** 自动分配的项目本地目录，只读。 */
  dataset_prefix?: string;
  /** Id description: project id */
  id?: number;
  /** Name description: project name */
  name?: string;
  /** Description description: project description */
  description?: string;
  /** Tips description: project tips */
  tips?: string;
  /** Config description: project config content */
  config?: string;
  /** Media Type description: project media type: IMAGE, VIDEO, AUDIO */
  media_type?: MediaType;
  /** Status description: project status: DRAFT, IMPORTED, CONFIGURED, INPROGRESS, FINISHED */
  status?: ProjectStatus;

  stats: ProjectStatics;
  /** Created At description: project created at time */
  created_at?: string;
  /** Created By description: project created at time */
  created_by?: UserResp;
}

export interface ProjectResponseWithStatics {
  ai_algorithm?: 'yolo' | 'florence2' | 'grounding_dino_sam' | 'sam3';
  training_config?: TrainingParameters | null;
  ai_model_name?: string | null;
  dataset_prefix?: string;
  /** Id description: project id */
  id?: number;
  /** Name description: project name */
  name?: string;
  /** Description description: project description */
  description?: string;
  /** Tips description: project tips */
  tips?: string;
  /** Config description: project config content */
  config?: string;
  /** Media Type description: project media type: IMAGE, VIDEO, AUDIO */
  media_type?: MediaType;
  /** Status description: project status: DRAFT, IMPORTED, CONFIGURED, INPROGRESS, FINISHED */
  status?: ProjectStatus;
  /** Created At description: project created at time */
  created_at?: string;
  /** Created By description: project created at time */
  created_by?: UserResp;
  updaters?: UserResp[];
  stats?: ProjectStatics;
}

export enum ProjectStatus {
  DRAFT = 'DRAFT',
  IMPORTED = 'IMPORTED',
  CONFIGURED = 'CONFIGURED',
  INPROGRESS = 'INPROGRESS',
  FINISHED = 'FINISHED',
}

export interface ProjectListResponseWithStatics {
  meta_data?: MetaData;
  /** Data */
  data: ProjectResponseWithStatics[];
}

export interface ProjectStatics {
  train?: number;
  test?: number;
  /** New description: count for project data have not labeled yet */
  new?: number;
  /** Done description: count for project data already labeled */
  done?: number;
  /** Skipped description: count for project data skipped */
  skipped?: number;
}

export interface UpdateApiV1ProjectsProjectIdPatchParams {
  project_id: number;
}

export interface UpdateApiV1ProjectsProjectIdSamplesSampleIdPatchParams {
  project_id: number;
  sample_id: number;
}

export interface UpdateCommand {
  ai_algorithm?: 'yolo' | 'florence2' | 'grounding_dino_sam' | 'sam3';
  training_config?: TrainingParameters | null;
  /** 自动标注的权重文件名或官方模型 ID。 */
  ai_model_name?: string | null;
  /** Name description: project name */
  name?: string;
  /** Description description: project description */
  description?: string;
  /** Tips description: project tips */
  tips?: string;
  /** description: project config content */
  media_type?: MediaType;
  /** Config description: project config content */
  config?: string;
}

export interface UserResp {
  /** Id */
  id?: number;
  /** Username */
  username?: string;
}

export interface ValidationError {
  /** Location */
  loc: any[];
  /** Message */
  msg: string;
  /** Error Type */
  type: string;
}

interface TextTool {
  /**
   * 唯一标识
   */
  id?: string;
  /**
   * 文本类型: text（文本）
   */
  type?: 'text';
  /**
   * 文本内容
   */
  value?: Record<string, string>;
}

interface TagTool {
  /**
   * 唯一标识
   */
  id?: string;
  type?: 'tag';
  value?: Record<string, string[]>;
}

export interface ParsedResult {
  relationTool?: { toolName?: 'relationTool'; result?: AnnotationData[] };
  pointTool?: PointResult;
  rectTool?: RectResult;
  polygonTool?: PolygonResult;
  lineTool?: LineResult;
  cuboidTool?: CuboidResult;
  videoSegmentTool?: VideoSegmentResult;
  videoFrameTool?: VideoFrameResult;
  audioSegmentTool?: AudioSegmentResult;
  audioFrameTool?: AudioFrameResult;
  textTool?: TextResult;
  tagTool?: TagResult;
}

export interface PointResult {
  toolName?: 'pointTool';
  result?: PointTool[];
}

export interface RectResult {
  toolName?: 'rectTool';
  result?: RectTool[];
}

export interface PolygonResult {
  toolName?: 'polygonTool';
  result?: PolygonTool[];
}

export interface LineResult {
  toolName?: 'lineTool';
  result?: GeneratedSchemaForRoot[];
}

export interface CuboidResult {
  toolName?: 'cuboidTool';
  result?: CuboidTool[];
}

export interface VideoSegmentResult {
  toolName?: 'videoSegmentTool';
  result?: SegmentTool[];
}

export interface VideoFrameResult {
  toolName?: 'videoFrameTool';
  result?: FrameTool[];
}

export interface AudioSegmentResult {
  toolName?: 'audioSegmentTool';
  result?: SegmentTool[];
}

export interface AudioFrameResult {
  toolName?: 'audioFrameTool';
  result?: FrameTool[];
}

export interface TextResult {
  toolName?: 'textTool';
  result?: TextTool[];
}

export interface TagResult {
  toolName?: 'tagTool';
  result?: TagTool[];
}

export interface PreAnnotationType {
  /**
   * The name of the sample file.
   */
  sample_name: string;
  config: {
    pointTool?: ILabel[];
    rectTool?: ILabel[];
    polygonTool?: ILabel[];
    lineTool?: ILabel[];
    cuboidTool?: ILabel[];
    videoSegmentTool?: ILabel[];
    videoFrameTool?: ILabel[];
    audioSegmentTool?: ILabel[];
    audioFrameTool?: ILabel[];
    textTool?: TextAttribute[];
    tagTool?: EnumerableAttribute[];
  };
  meta_data?: {
    width?: number;
    height?: number;
    rotate?: number;
    duration?: number;
  };
  annotations: {
    pointTool?: PointResult;
    rectTool?: RectResult;
    polygonTool?: PolygonResult;
    lineTool?: LineResult;
    cuboidTool?: CuboidResult;
    videoSegmentTool?: VideoSegmentResult;
    videoFrameTool?: VideoFrameResult;
    audioSegmentTool?: AudioSegmentResult;
    audioFrameTool?: AudioFrameResult;
    textTool?: TextResult;
    tagTool?: TagResult;
  };
}

interface PointTool {
  /**
   * 唯一标识
   */
  id: string;
  /**
   * x坐标
   */
  x: number;
  /**
   * y坐标
   */
  y: number;
  /**
   * 是否可见
   */
  visible?: boolean;
  attributes?: Attribute;
  /**
   * 标注顺序
   */
  order: number;
  /**
   * 标注类别
   */
  label: string;
}
/**
 * 类别属性，键值对
 */
export type Attribute = Record<string, string | string[]>;
export interface RectTool {
  /**
   * 唯一标识
   */
  id: string;
  /**
   * 拉框左上角x坐标
   */
  x: number;
  /**
   * 拉框左上角y坐标
   */
  y: number;
  /**
   * 拉框宽度
   */
  width: number;
  /**
   * 拉框高度
   */
  height: number;
  /**
   * 是否可见
   */
  visible?: boolean;
  attributes?: Attribute;
  /**
   * 标注顺序
   */
  order: number;
  /**
   * 标注类别
   */
  label: string;
}
export interface PolygonTool {
  /**
   * 唯一标识
   */
  id: string;
  /**
   * 线条类型: line（直线），spline（曲线）
   */
  lineType: 'line' | 'spline';
  /**
   * 控制点列表
   */
  controlPoints?: Point[];
  /**
   * 线条点列表
   */
  points: Point[];
  /**
   * 是否可见
   */
  visible?: boolean;
  attributes?: Attribute;
  /**
   * 标注顺序
   */
  order: number;
  /**
   * 标注类别
   */
  label: string;
}
export interface Point {
  /**
   * x坐标
   */
  x: number;
  /**
   * y坐标
   */
  y: number;
}
export interface GeneratedSchemaForRoot {
  /**
   * 唯一标识
   */
  id: string;
  /**
   * 线条类型: line（直线），spline（曲线）
   */
  lineType: 'line' | 'spline';
  /**
   * 控制点列表
   */
  controlPoints?: Point[];
  /**
   * 线条点列表
   */
  points: Point[];
  /**
   * 是否可见
   */
  visible?: boolean;
  attributes?: Attribute;
  /**
   * 标注顺序
   */
  order: number;
  /**
   * 标注类别
   */
  label: string;
}
export interface CuboidTool {
  /**
   * 唯一标识
   */
  id: string;
  /**
   * 正面方向: front（前面），back（后面），left（左侧面），right（右侧面）
   */
  direction: string;
  /**
   * 正面四个点坐标
   */
  front: {
    /**
     * 左上角坐标
     */
    tl: {
      x: number;
      y: number;
    };
    /**
     * 右上角坐标
     */
    tr: {
      x: number;
      y: number;
    };
    /**
     * 右下角坐标
     */
    br: {
      x: number;
      y: number;
    };
    /**
     * 左下角坐标
     */
    bl: {
      x: number;
      y: number;
    };
  };
  /**
   * 背面四个点坐标
   */
  back: {
    /**
     * 左上角坐标
     */
    tl: {
      x: number;
      y: number;
    };
    /**
     * 右上角坐标
     */
    tr: {
      x: number;
      y: number;
    };
    /**
     * 右下角坐标
     */
    br: {
      x: number;
      y: number;
    };
    /**
     * 左下角坐标
     */
    bl: {
      x: number;
      y: number;
    };
  };
  /**
   * 是否可见
   */
  visible?: boolean;
  attributes?: Attribute;
  /**
   * 标注顺序
   */
  order: number;
  /**
   * 标注类别
   */
  label: string;
}
export interface SegmentTool {
  /**
   * 唯一标识
   */
  id: string;
  /**
   * 时间点
   */
  time?: number;
  /**
   * 标注顺序
   */
  order: number;
  /**
   * 标注类别
   */
  label: string;
  attributes?: Attribute;
}
export interface FrameTool {
  /**
   * 唯一标识
   */
  id: string;
  /**
   * 时间点
   */
  time?: number;
  /**
   * 标注顺序
   */
  order: number;
  /**
   * 标注类别
   */
  label: string;
  attributes?: Attribute;
}
