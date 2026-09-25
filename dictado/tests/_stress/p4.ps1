Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = -1
$s.SetOutputToWaveFile("C:\\PROYECTOS\\Instant\\dictado\\tests\\_stress\\p4.wav")
$s.Speak("The five boxing wizards jump quickly over the heavy wooden fence.")
$s.Dispose()
