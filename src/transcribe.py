import whisper
import json

def transcribe_audio(audio_path: str, model_name: str = "small"):
    # Загружаем модель Whisper
    model = whisper.load_model(model_name)

    print(f"Transcribing {audio_path} ...")
    # Получаем результат
    result = model.transcribe(audio_path, word_timestamps=True)

    # Сохраняем текст + таймкоды в JSON
    output_json = audio_path.replace(".wav", "_transcript.json")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Done! Transcript saved to {output_json}")
    return result

if __name__ == "__main__":
    transcript = transcribe_audio("data/audio.wav")
