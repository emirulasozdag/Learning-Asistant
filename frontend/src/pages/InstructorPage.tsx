import FrequentMistakes from "../features/instructor/FrequentMistakes";
import MaterialUpload from "../features/instructor/MaterialUpload";
import ReviewQueue from "../features/instructor/ReviewQueue";
import RubricEditor from "../features/instructor/RubricEditor";

export default function InstructorPage() {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <MaterialUpload />
      <FrequentMistakes />
      <RubricEditor />
      <ReviewQueue />
    </div>
  );
}
