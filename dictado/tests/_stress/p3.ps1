Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = -1
$s.SetOutputToWaveFile("C:\\PROYECTOS\\Instant\\dictado\\tests\\_stress\\p3.wav")
$s.Speak("How vexingly quick daft zebras jump across the frozen meadow.")
$s.Dispose()
