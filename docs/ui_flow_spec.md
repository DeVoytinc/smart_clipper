# Smart Clipper UI Flow Spec

## Product Jobs

1. Import video from source (Rutube URL or local file).
2. Generate best moments automatically.
3. Review and trim selected clips quickly.
4. Export and download final clips.

## Information Architecture

- `/` Projects dashboard
- `/editor/:projectId` Project workspace

## Dashboard Wireframe

```
+-------------------------------------------------------------+
| Smart Clipper                           Recent Projects ... |
+-------------------------------------------------------------+
| Step 1: Source                                             |
| [Rutube URL] [Local File]                                  |
| if Rutube: [URL input] [Import Video]                      |
| if Local : [Choose file] [Import Video]                    |
| Progress + status                                           |
|-------------------------------------------------------------|
| Step 2: Create Project                                     |
| [Project Name] [Create Project]                            |
+-------------------------------------------------------------+
| Recent project cards                                       |
+-------------------------------------------------------------+
```

## Editor Wireframe

```
+-------------------------------------------------------------+
| Project Name                 [Generate] [Review] [Export]  |
+-------------------------------------------------------------+
| Left panel          | Center preview + timeline | Right     |
| Clip list (ranked)  | Active clip playback      | Inspector |
| Keep/Discard        | Trim start/end             | Metadata  |
+-------------------------------------------------------------+
| Export step: selected clip count + Export Selected button  |
| Export results list                                        |
+-------------------------------------------------------------+
```

## Component Map

- `Dashboard`
- `ProjectEditor`
- `features/project-flow/PhaseStepper`
- `features/project-flow/ClipList`
- `features/editor/useFrames`
- `features/editor/utils`

## Frontend State Model

### Dashboard
- `sourceMode`: `"rutube" | "local"`
- `sourceUrl`: `string`
- `localFile`: `File | null`
- `importJobId`: `string`
- `importProgress`: `{ value, label, eta, speed, total, logs }`
- `importedVideo`: `{ path, url, fileName, sourceType } | null`
- `projectName`: `string`
- `projects`: `Project[]`
- `status`: `string`

### ProjectEditor
- `phase`: `"generate" | "review" | "export"`
- `project`: `Project | null`
- `selector`: `"both" | "llm" | "heuristic"`
- `count`: `string`
- `clips`: `ClipDraft[]` with `{ kept: boolean, score: number }` on client
- `activeClipId`: `string`
- `duration/currentTime/zoom`
- `isAnalyzing/isSaving/isProjectSaving`
- `exported`: `ExportedClip[]`
- `status`: `string`

## API Contract Use

- `POST /api/download`
- `GET /api/status?id=...`
- `POST /api/upload`
- `POST /api/project/create`
- `GET /api/project?id=...`
- `POST /api/analyze`
- `POST /api/project/save`
- `POST /api/export`

## UX Rules

1. One primary action per step.
2. Disable next step until previous step is complete.
3. Always show operation status (start, running, done, failed).
4. In review mode, keep/discard and trim must be one-click operations.
5. Export only selected (`kept`) clips.
