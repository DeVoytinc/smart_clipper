export default function PhaseStepper({ phase, onChange }) {
  const items = [
    { id: "generate", title: "1. Generate" },
    { id: "review", title: "2. Review" },
    { id: "export", title: "3. Export" },
  ];

  return (
    <div className="phase-stepper">
      {items.map((item) => (
        <button
          key={item.id}
          className={`phase-step ${phase === item.id ? "active" : ""}`}
          onClick={() => onChange(item.id)}
        >
          {item.title}
        </button>
      ))}
    </div>
  );
}
