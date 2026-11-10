import _ from 'lodash';
import type { AnnotationsWithGlobal, MediaSample } from '@yolo-mcp/audio-annotator-react';

import type { ParsedResult, SampleResponse } from '@/api/types';
import { MediaType } from '@/api/types';

import { jsonParse } from './index';

export function convertMediaAnnotations(mediaType: MediaType, result: ParsedResult) {
  // annotation
  const pool = [
    ['segment', MediaType.VIDEO === mediaType ? 'videoSegmentTool' : 'audioSegmentTool'],
    ['frame', MediaType.VIDEO === mediaType ? 'videoFrameTool' : 'audioFrameTool'],
    ['text', 'textTool'],
    ['tag', 'tagTool'],
  ] as const;

  return _.chain(pool)
    .map(([type, key]) => {
      const items = result[key]?.result ?? [];

      return [
        type,
        items.map((item) => {
          return {
            ...item,
            type,
          };
        }),
      ];
    })
    .fromPairs()
    .value() as AnnotationsWithGlobal;
}

export function convertAudioAndVideoSample(sample: SampleResponse, mediaType?: MediaType): MediaSample | undefined {
  if (!sample) {
    return;
  }

  const id = sample.id!;

  let resultParsed: any = {};
  if (sample?.data?.result && !_.isNull(sample?.data?.result)) {
    resultParsed = jsonParse(sample.data.result);
  }

  return {
    id,
    url: [MediaType.VIDEO, MediaType.AUDIO].includes(mediaType as MediaType)
      ? sample.file.url.replace('attachment', 'partial')
      : sample.file.url,
    data: convertMediaAnnotations(mediaType!, resultParsed),
  };
}
