import ChatPanel from "../features/qa/ChatPanel";
import FeedbackPanel from "../features/feedback/FeedbackPanel";
import LearningRecordPanel from "../features/learning/LearningRecordPanel";
import PracticePanel from "../features/practice/PracticePanel";
import SourceViewer from "../features/sources/SourceViewer";
import VideoPlayer from "../features/video/VideoPlayer";

export default function StudentPage() {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <VideoPlayer />
        <SourceViewer />
      </div>
      <div className="flex flex-col gap-4">
        <ChatPanel />
        <PracticePanel />
        <FeedbackPanel />
        <LearningRecordPanel />
      </div>
    </div>
  );
}
