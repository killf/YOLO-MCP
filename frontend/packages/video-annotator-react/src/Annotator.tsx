import VideoAnnotator from '@yolo-mcp/video-react';
import { forwardRef } from 'react';
import { MediaAnnotatorWrapper } from '@yolo-mcp/audio-annotator-react';
import type { AudioAndVideoAnnotatorRef, AnnotatorProps } from '@yolo-mcp/audio-annotator-react';

function ForwardAnnotator({ samples, ...props }: AnnotatorProps, ref: React.Ref<AudioAndVideoAnnotatorRef>) {
  return (
    <MediaAnnotatorWrapper samples={samples} ref={ref} {...props}>
      {(annotatorProps) => <VideoAnnotator {...annotatorProps} className="yolo-mcp-video-wrapper" />}
    </MediaAnnotatorWrapper>
  );
}

export const Annotator = forwardRef<AudioAndVideoAnnotatorRef, AnnotatorProps>(ForwardAnnotator);
