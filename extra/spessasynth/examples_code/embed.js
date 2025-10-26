import { Sequencer, WorkletSynthesizer } from "../../src/index.ts";
import { EXAMPLE_SOUND_BANK_PATH, EXAMPLE_WORKLET_PATH } from "../examples_common.js";

const messageEl = document.getElementById("message");

messageEl.innerText = "Please wait for the sound bank to load.";

// load the sound bank
fetch(EXAMPLE_SOUND_BANK_PATH).then(async (response) => {
    // load the sound bank into an array buffer
    let sfBuffer = await response.arrayBuffer();
    messageEl.innerText = "Sound bank has been loaded!";

    // create the context and add audio worklet
    const context = new AudioContext();
    await context.audioWorklet.addModule(EXAMPLE_WORKLET_PATH);
    const synth = new WorkletSynthesizer(context); // create the synthesizer
    synth.connect(context.destination);
    await synth.soundBankManager.addSoundBank(sfBuffer, "main");
    let seq = new Sequencer(synth);

    const fileName = new URLSearchParams(location.search).get('midi');

    if (fileName) {
        messageEl.innerText = "Please wait for the MIDI to load.";
    } else {
        messageEl.innerText = "No MIDI file provided!";
        return;
    }

    // parse all the files
    const parsedSongs = [];
    fetch(fileName).then(async response => {

        if (!response.ok) {
            messageEl.innerText = "Error loading the MIDI file!";
            return;
        }

        parsedSongs.push({
            binary: await response.arrayBuffer(),
            fileName, // fallback name if the MIDI doesn't have one
        });
        seq.loadNewSongList(parsedSongs); // load the song list

        // make the slider move with the song
        let slider = document.getElementById("progress");
        setInterval(() => {
            // slider ranges from 0 to 1000
            slider.value = (seq.currentTime / seq.duration) * 1000;
        }, 100);

        // on song change, show the name
        seq.eventHandler.addEvent(
            "songChange",
            "example-time-change",
            (e) => messageEl.innerText = "Now playing: " + e.getName(),
        ); // make sure to add a unique id!

        // add time adjustment
        slider.onchange = () => {
            // calculate the time
            seq.currentTime = (slider.value / 1000) * seq.duration; // switch the time (the sequencer adjusts automatically)
        };

        const pauseButton = document.getElementById("pause");

        // on pause click
        pauseButton.onclick = async () => {
            if (seq.paused) {
                await context.resume();
                pauseButton.innerText = "Pause";
                seq.play(); // resume
            } else {
                pauseButton.innerText = "Resume";
                seq.pause(); // pause
            }
        };

        pauseButton.disabled = false;

        document.getElementById("message").innerText = "MIDI has been loaded!";

    });
});
