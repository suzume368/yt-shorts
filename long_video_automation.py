def generate_voice_long(text, audio_path, ass_path):
    """Generate English TTS using Google Cloud Text-to-Speech (FREE tier)."""
    import os
    from google.oauth2 import service_account
    
    # Try to use service account credentials from environment variable first
    credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_json and os.path.exists(credentials_json):
        credentials = service_account.Credentials.from_service_account_file(credentials_json)
        client = texttospeech.TextToSpeechClient(credentials=credentials)
    else:
        # Fall back to default credentials (Application Default Credentials)
        client = texttospeech.TextToSpeechClient()
    
    synthesis_input = texttospeech.SynthesisInput(text=text)
    
    # Use English voice - Neural (faster, better quality) or Standard
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Neural2-C",  # Professional male English voice
        ssml_gender=texttospeech.SsmlVoiceGender.MALE,
    )
    
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        pitch=0.0,
        speaking_rate=1.0,
    )
    
    request = texttospeech.SynthesizeSpeechRequest(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
        enable_time_pointing=[texttospeech.SynthesizeSpeechRequest.TextToSpeechFeature.SSML_DIALECT],
    )
    
    response = client.synthesize_speech(request=request)
    
    # Save audio file
    with open(audio_path, "wb") as out:
        out.write(response.audio_content)
    
    print(f"[voice] Ses olusturuldu -> {Path(audio_path).name}")
    
    # Get duration using ffprobe
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(out.stdout.strip())
    
    # Simple word timing: distribute duration across words
    words = text.split()
    word_duration = duration / len(words) if words else 0
    
    cues = []
    current_time = 0.0
    for word in words:
        cues.append(_WordCue(word, current_time, current_time + word_duration))
        current_time += word_duration
    
    _build_ass_long(cues, ass_path)
    
    print(f"[voice] {duration:.1f}s ses uretildi -> {Path(audio_path).name}")
    return duration, cues
