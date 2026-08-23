#include <Arduino.h>
#include <ArduinoOTA.h>
#include <Preferences.h>
#include <SoftwareSerial.h>
#include <Update.h>
#include <WebServer.h>
#include <WiFi.h>
#include <soc/gpio_struct.h>
#include "wifi_config.h"

namespace {

constexpr char AP_SSID[] = "UART-LOGGER";
constexpr char AP_PASSWORD[] = "uartlogger";
constexpr char HOSTNAME[] = "uart-logger";
constexpr uint8_t HARDWARE_CHANNEL_COUNT = 3;
constexpr uint8_t CHANNEL_COUNT = 4;
constexpr int RX_PINS[CHANNEL_COUNT] = {16, 17, 32, 33};
constexpr int UNUSED_TX_PINS[HARDWARE_CHANNEL_COUNT] = {25, 26, 27};
constexpr size_t EVENT_CAPACITY = 300;
constexpr size_t CHUNK_SIZE = 64;
constexpr uint32_t RAW_TICK_NS = 250;
constexpr size_t RAW_EVENT_CAPACITY = 96;
constexpr size_t RAW_PULSE_CAPACITY = 64;
constexpr size_t RAW_ISR_BUFFER_CAPACITY = 512;

struct CaptureEvent {
  uint32_t sequence;
  uint32_t microseconds;
  uint8_t channel;
  uint8_t length;
  uint8_t data[CHUNK_SIZE];
};

struct ChannelConfig {
  uint32_t baud;
  uint32_t serialConfig;
  const char *formatName;
};

struct PendingCapture {
  uint32_t startedAt;
  uint32_t lastByteAt;
  uint8_t length;
  uint8_t data[CHUNK_SIZE];
};

struct RawEdgeEvent {
  uint32_t sequence;
  uint32_t microseconds;
  uint8_t channel;
  uint8_t pulseCount;
  uint32_t pulses[RAW_PULSE_CAPACITY];
};

struct RawIsrSample {
  uint32_t cycles;
  uint32_t microsecondsAndLevel;
};

struct RawPendingCapture {
  uint32_t startedAt;
  uint8_t pulseCount;
  uint32_t pulses[RAW_PULSE_CAPACITY];
};

WebServer server(80);
Preferences preferences;
HardwareSerial uart1(1);
HardwareSerial uart2(2);
HardwareSerial *hardwareUarts[HARDWARE_CHANNEL_COUNT] = {&uart1, &uart2, &Serial};
EspSoftwareSerial::UART softwareUart;
ChannelConfig configs[CHANNEL_COUNT];
String channelNames[CHANNEL_COUNT];
PendingCapture pending[CHANNEL_COUNT]{};
CaptureEvent events[EVENT_CAPACITY];
size_t eventHead = 0;
size_t eventCount = 0;
uint32_t nextSequence = 1;
uint32_t restartAt = 0;
bool httpUpdateAuthorized = false;
uint32_t softwareOverflowCount = 0;
RawEdgeEvent rawEvents[RAW_EVENT_CAPACITY];
RawPendingCapture rawPending[CHANNEL_COUNT]{};
RawIsrSample rawIsrBuffers[CHANNEL_COUNT][RAW_ISR_BUFFER_CAPACITY];
volatile uint16_t rawIsrHeads[CHANNEL_COUNT]{};
volatile uint16_t rawIsrTails[CHANNEL_COUNT]{};
volatile uint32_t rawInputOverflowCounts[CHANNEL_COUNT]{};
uint32_t rawLastCycles[CHANNEL_COUNT]{};
uint32_t rawLastMicroseconds[CHANNEL_COUNT]{};
uint8_t rawLastLevels[CHANNEL_COUNT]{};
size_t rawEventHead = 0;
size_t rawEventCount = 0;
uint32_t nextRawSequence = 1;
uint32_t rawEvictedCount = 0;

const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32 UART Logger</title>
<style>
:root{color-scheme:dark;--bg:#0b1018;--card:#151d29;--line:#273447;--ink:#e8eef7;--muted:#9aabc0;--accent:#42d392}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px system-ui,sans-serif}
main{max-width:1000px;margin:auto;padding:16px}h1{font-size:22px;margin:4px 0 6px}.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
label{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}select,input,button{width:100%;border:1px solid var(--line);border-radius:8px;background:#0e1520;color:var(--ink);padding:9px}
button{background:var(--accent);border:0;color:#052317;font-weight:700;cursor:pointer}.actions{display:flex;gap:8px}.actions button{width:auto}
#log{height:56vh;overflow:auto;white-space:pre-wrap;word-break:break-all;background:#070b11;border-radius:8px;padding:10px;font:13px ui-monospace,Consolas,monospace}
.ch1{color:#61dafb}.ch2{color:#ffd166}.ch3{color:#ef88d5}.ch4{color:#ff9f43}.status{float:right;color:var(--accent)}
</style></head><body><main>
<h1>ESP32 UART Logger <span id="status" class="status">łączenie…</span></h1>
<div class="muted">4 wejścia RX · 3 sprzętowe + 1 programowe · czas od uruchomienia ESP32</div>
<section class="card"><div id="network" class="muted">Ładowanie informacji o sieci…</div><div class="grid" style="margin-top:10px"><div><label>Nazwa sieci Wi-Fi 2,4 GHz</label><input id="ssid" autocomplete="off"></div><div><label>Hasło Wi-Fi</label><input id="wifiPassword" type="password" autocomplete="new-password" placeholder="pozostaw puste, aby nie zmieniać"></div></div><div class="actions" style="margin-top:10px"><button onclick="saveNetwork()">Zapisz Wi-Fi i uruchom ponownie</button><button onclick="location.href='/update'">Aktualizacja OTA</button></div></section>
<section class="card"><div class="grid" id="channels"></div><div style="margin-top:10px"><button onclick="saveConfig()">Zapisz konfigurację</button></div></section>
<section class="card"><div class="actions"><button onclick="startRecording()" id="record">● Rozpocznij nagrywanie</button><button onclick="stopRecording()" id="stop" disabled>Zatrzymaj</button><button onclick="downloadRecording()" id="download" disabled>Pobierz .jsonl</button></div><p id="recordStats" class="muted">Nagrywanie w pamięci telefonu: wyłączone</p></section>
<section class="card"><strong>Surowe zbocza — do wykrywania prędkości i formatu UART</strong><div class="actions" style="margin-top:10px"><button onclick="startRawRecording()" id="rawRecord">● Nagrywaj zbocza</button><button onclick="stopRawRecording()" id="rawStop" disabled>Zatrzymaj</button><button onclick="downloadRawRecording()" id="rawDownload" disabled>Pobierz raw .jsonl</button></div><p id="rawStats" class="muted">Nagrywanie surowe: wyłączone · rozdzielczość 0,25 µs</p></section>
<section class="card"><div class="actions"><button onclick="clearView()">Wyczyść widok</button><button onclick="togglePause()" id="pause">Pauza</button></div><p class="muted">Format: czas, kanał, HEX oraz ASCII. Puste kropki oznaczają bajty niedrukowalne.</p><div id="log"></div></section>
</main><script>
let after=0,afterInitialized=false,paused=false,lines=[],recording=false,recorded=[],recordedBytes=0,dropped=0,recordStarted=null,wakeLock=null,currentConfig=[];
let rawAfter=0,rawInitialized=false,rawRecording=false,rawRecorded=[],rawBytes=0,rawDropped=0,rawStarted=null,rawInputOverflow=0,rawOverflowBaseline=0;
const statusEl=document.getElementById('status'),logEl=document.getElementById('log'),channelsEl=document.getElementById('channels'),networkEl=document.getElementById('network'),ssidEl=document.getElementById('ssid'),wifiPasswordEl=document.getElementById('wifiPassword'),pauseBtn=document.getElementById('pause'),recordBtn=document.getElementById('record'),stopBtn=document.getElementById('stop'),downloadBtn=document.getElementById('download'),recordStatsEl=document.getElementById('recordStats'),rawRecordBtn=document.getElementById('rawRecord'),rawStopBtn=document.getElementById('rawStop'),rawDownloadBtn=document.getElementById('rawDownload'),rawStatsEl=document.getElementById('rawStats'),pins=[16,17,32,33],bauds=[1200,2400,4800,9600,19200,38400,57600,115200,230400,460800,921600],formats=['8N1','8E1','8O1','7E1','7O1','8N2'];
function safe(s){return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;')}
function controls(cfg){currentConfig=cfg;let h='';for(let i=0;i<4;i++){h+=`<div><label>Kanał ${i+1} — GPIO${pins[i]}${i===3?' (programowy)':''}</label><input id="n${i}" maxlength="24" value="${safe(cfg[i].name)}" placeholder="np. płyta → wyświetlacz"><select id="b${i}" style="margin-top:6px">${bauds.map(x=>`<option ${x==cfg[i].baud?'selected':''}>${x}</option>`).join('')}</select><select id="f${i}" style="margin-top:6px">${formats.map(x=>`<option ${x==cfg[i].format?'selected':''}>${x}</option>`).join('')}</select></div>`}channelsEl.innerHTML=h}
async function loadConfig(){let r=await fetch('/api/config');controls(await r.json())}
async function loadNetwork(){let r=await fetch('/api/network'),n=await r.json();ssidEl.value=n.ssid;networkEl.textContent=n.connected?`Połączono z ${n.ssid} · IP: ${n.ip} · OTA: ${n.host}.local · sygnał: ${n.rssi} dBm`:`Brak połączenia z routerem · awaryjny panel: ${n.apIp}`}
async function saveNetwork(){let p=new URLSearchParams({ssid:ssidEl.value,password:wifiPasswordEl.value});let r=await fetch('/api/network',{method:'POST',body:p});if(r.ok){statusEl.textContent='restart…';networkEl.textContent='Zapisano. ESP32 uruchamia się ponownie…'}else alert(await r.text())}
async function saveConfig(){let p=new URLSearchParams();for(let i=0;i<4;i++){p.set('n'+i,document.getElementById('n'+i).value);p.set('b'+i,document.getElementById('b'+i).value);p.set('f'+i,document.getElementById('f'+i).value)}let r=await fetch('/api/config',{method:'POST',body:p});if(r.ok){currentConfig=await r.json();controls(currentConfig);statusEl.textContent='zapisano';setTimeout(()=>statusEl.textContent='online',1200)}else alert(await r.text())}
function clearView(){lines=[];logEl.textContent=''}function togglePause(){paused=!paused;pauseBtn.textContent=paused?'Wznów':'Pauza'}
function channelLabel(ch){let c=currentConfig[ch-1],name=c&&c.name?c.name:`CH${ch}`;return `${name} [CH${ch}]`}
function add(e){let sec=(e.us/1e6).toFixed(6).padStart(13,' '),ascii=e.ascii.replace(/</g,'&lt;').replace(/>/g,'&gt;');lines.push(`<span class="ch${e.ch}">${sec}  ${safe(channelLabel(e.ch))}  ${e.hex.padEnd(192,' ')} |${ascii}|</span>`);if(lines.length>500)lines.splice(0,80)}
function updateRecordStats(){let seconds=recordStarted?((Date.now()-recordStarted)/1000).toFixed(1):'0.0';recordStatsEl.textContent=recording?`Nagrywanie: ${seconds} s · ${recorded.length} rekordów · ${recordedBytes} bajtów · luki: ${dropped}`:`Nagranie zatrzymane · ${recorded.length} rekordów · ${recordedBytes} bajtów · luki: ${dropped}`}
async function startRecording(){recorded=[];recordedBytes=0;dropped=0;recordStarted=Date.now();recording=true;recordBtn.disabled=true;stopBtn.disabled=false;downloadBtn.disabled=true;try{if(navigator.wakeLock)wakeLock=await navigator.wakeLock.request('screen')}catch(e){}updateRecordStats()}
async function stopRecording(){recording=false;recordBtn.disabled=false;stopBtn.disabled=true;downloadBtn.disabled=recorded.length===0;if(wakeLock){try{await wakeLock.release()}catch(e){}wakeLock=null}updateRecordStats()}
function downloadRecording(){if(!recorded.length)return;let meta={type:'uart-logger',version:1,started:new Date(recordStarted).toISOString(),channels:currentConfig,dropped};let text=JSON.stringify(meta)+'\n'+recorded.map(e=>JSON.stringify({seq:e.seq,us:e.us,ch:e.ch,hex:e.hex})).join('\n')+'\n';let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'application/x-ndjson'}));a.download=`uart-${new Date(recordStarted).toISOString().replace(/[:.]/g,'-')}.jsonl`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}
function updateRawStats(){let seconds=rawStarted?((Date.now()-rawStarted)/1000).toFixed(1):'0.0',edgeLoss=rawInputOverflow-rawOverflowBaseline;rawStatsEl.textContent=rawRecording?`Surowe zbocza: ${seconds} s · ${rawRecorded.length} bloków · około ${rawBytes} bajtów · luki rekordów: ${rawDropped} · zgubione zbocza: ${edgeLoss}`:`Nagranie surowe zatrzymane · ${rawRecorded.length} bloków · około ${rawBytes} bajtów · luki rekordów: ${rawDropped} · zgubione zbocza: ${edgeLoss}`}
async function startRawRecording(){rawRecorded=[];rawBytes=0;rawDropped=0;rawOverflowBaseline=rawInputOverflow;rawStarted=Date.now();rawRecording=true;rawRecordBtn.disabled=true;rawStopBtn.disabled=false;rawDownloadBtn.disabled=true;updateRawStats()}
function stopRawRecording(){rawRecording=false;rawRecordBtn.disabled=false;rawStopBtn.disabled=true;rawDownloadBtn.disabled=rawRecorded.length===0;updateRawStats()}
function downloadRawRecording(){if(!rawRecorded.length)return;let meta={type:'uart-edge-logger',version:2,started:new Date(rawStarted).toISOString(),tick_ns:250,encoding:'uint32-hex: bit31=level, bits0-30=duration_ticks',channels:currentConfig,dropped_records:rawDropped,dropped_edges:rawInputOverflow-rawOverflowBaseline};let text=JSON.stringify(meta)+'\n'+rawRecorded.map(e=>JSON.stringify({seq:e.seq,us:e.us,ch:e.ch,raw:e.raw})).join('\n')+'\n';let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'application/x-ndjson'}));a.download=`uart-edges-${new Date(rawStarted).toISOString().replace(/[:.]/g,'-')}.jsonl`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}
async function rawPoll(){try{let url=rawInitialized?'/api/raw?after='+rawAfter:'/api/raw?latest=1',r=await fetch(url,{cache:'no-store'}),d=await r.json();rawInputOverflow=d.inputOverflow||0;if(!rawInitialized){rawAfter=d.latest||0;rawInitialized=true}if(rawRecording&&d.events.length&&rawAfter&&d.events[0].seq>rawAfter+1)rawDropped+=d.events[0].seq-rawAfter-1;for(const e of d.events){rawAfter=Math.max(rawAfter,e.seq);if(rawRecording){rawRecorded.push(e);rawBytes+=Math.ceil(e.raw.length/2)+16}}if(rawBytes>16000000&&rawRecording)stopRawRecording();if(rawRecording)updateRawStats()}catch(e){}setTimeout(rawPoll,250)}
async function poll(){try{let url=afterInitialized?'/api/data?after='+after:'/api/data?latest=1',r=await fetch(url,{cache:'no-store'}),d=await r.json();if(!afterInitialized){after=d.latest||0;afterInitialized=true}if(recording&&d.events.length&&after&&d.events[0].seq>after+1)dropped+=d.events[0].seq-after-1;for(const e of d.events){after=Math.max(after,e.seq);if(recording){recorded.push(e);recordedBytes+=e.hex?Math.ceil(e.hex.length/3):0}if(!paused)add(e)}if(recordedBytes>16000000&&recording)await stopRecording();if(!paused){logEl.innerHTML=lines.join('\n');logEl.scrollTop=logEl.scrollHeight}statusEl.textContent=`online${d.softOverflow?' · CH4 overflow: '+d.softOverflow:''}`;if(recording)updateRecordStats()}catch(e){statusEl.textContent='brak połączenia'}setTimeout(poll,150)}
Promise.all([loadConfig(),loadNetwork()]).then(()=>{poll();rawPoll()});
</script></body></html>
)HTML";

const char UPDATE_HTML[] PROGMEM = R"HTML(
<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aktualizacja UART Logger</title><style>body{max-width:620px;margin:40px auto;padding:16px;background:#0b1018;color:#e8eef7;font:16px system-ui}section{background:#151d29;border:1px solid #273447;border-radius:12px;padding:18px}input,button{width:100%;box-sizing:border-box;margin-top:12px;padding:12px;border-radius:8px;border:1px solid #273447}button{background:#42d392;color:#052317;font-weight:700}</style></head>
<body><section><h2>Aktualizacja OTA</h2><p>Wybierz skompilowany plik <code>firmware.bin</code>. Nie odłączaj zasilania podczas aktualizacji.</p><form method="POST" action="/api/update" enctype="multipart/form-data"><input type="file" name="firmware" accept=".bin" required><button type="submit">Wgraj i uruchom ponownie</button></form></section></body></html>
)HTML";

uint32_t serialConfigFromName(const String &name) {
  if (name == "8E1") return SERIAL_8E1;
  if (name == "8O1") return SERIAL_8O1;
  if (name == "7E1") return SERIAL_7E1;
  if (name == "7O1") return SERIAL_7O1;
  if (name == "8N2") return SERIAL_8N2;
  return SERIAL_8N1;
}

EspSoftwareSerial::Config softwareConfigFromName(const String &name) {
  if (name == "8E1") return EspSoftwareSerial::SWSERIAL_8E1;
  if (name == "8O1") return EspSoftwareSerial::SWSERIAL_8O1;
  if (name == "7E1") return EspSoftwareSerial::SWSERIAL_7E1;
  if (name == "7O1") return EspSoftwareSerial::SWSERIAL_7O1;
  if (name == "8N2") return EspSoftwareSerial::SWSERIAL_8N2;
  return EspSoftwareSerial::SWSERIAL_8N1;
}

const char *normalizedFormat(const String &name) {
  if (name == "8E1") return "8E1";
  if (name == "8O1") return "8O1";
  if (name == "7E1") return "7E1";
  if (name == "7O1") return "7O1";
  if (name == "8N2") return "8N2";
  return "8N1";
}

bool validBaud(uint32_t baud) {
  constexpr uint32_t allowed[] = {1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600};
  for (uint32_t item : allowed) if (item == baud) return true;
  return false;
}

void beginChannel(uint8_t channel) {
  pinMode(RX_PINS[channel], INPUT_PULLUP);
  pending[channel].length = 0;
  if (channel < HARDWARE_CHANNEL_COUNT) {
    HardwareSerial *uart = hardwareUarts[channel];
    uart->end();
    delay(5);
    uart->setRxBufferSize(2048);
    uart->begin(configs[channel].baud, configs[channel].serialConfig,
                RX_PINS[channel], UNUSED_TX_PINS[channel], false, 200);
  } else {
    softwareUart.end();
    delay(5);
    softwareUart.begin(configs[channel].baud,
                       softwareConfigFromName(configs[channel].formatName),
                       RX_PINS[channel], -1, false, 1024, 0);
  }
}

Stream &inputForChannel(uint8_t channel) {
  if (channel < HARDWARE_CHANNEL_COUNT) return *hardwareUarts[channel];
  return softwareUart;
}

void addEvent(uint8_t channel, const uint8_t *data, size_t length, uint32_t timestamp) {
  CaptureEvent &event = events[eventHead];
  event.sequence = nextSequence++;
  event.microseconds = timestamp;
  event.channel = channel + 1;
  event.length = static_cast<uint8_t>(min(length, CHUNK_SIZE));
  memcpy(event.data, data, event.length);
  eventHead = (eventHead + 1) % EVENT_CAPACITY;
  if (eventCount < EVENT_CAPACITY) ++eventCount;
}

void flushPending(uint8_t channel) {
  PendingCapture &item = pending[channel];
  if (!item.length) return;
  addEvent(channel, item.data, item.length, item.startedAt);
  item.length = 0;
}

void captureUarts() {
  for (uint8_t channel = 0; channel < CHANNEL_COUNT; ++channel) {
    Stream &input = inputForChannel(channel);
    PendingCapture &item = pending[channel];
    while (input.available()) {
      uint32_t now = micros();
      if (!item.length) item.startedAt = now;
      int value = input.read();
      if (value < 0) break;
      item.data[item.length++] = static_cast<uint8_t>(value);
      item.lastByteAt = now;
      if (item.length == CHUNK_SIZE) flushPending(channel);
    }
    uint32_t safeBaud = configs[channel].baud ? configs[channel].baud : 1;
    uint32_t idleThreshold = 20000000UL / safeBaud;
    if (idleThreshold < 3000) idleThreshold = 3000;
    if (item.length && static_cast<uint32_t>(micros() - item.lastByteAt) >= idleThreshold) flushPending(channel);
  }
  if (softwareUart.overflow()) ++softwareOverflowCount;
}

uint8_t IRAM_ATTR rawPinLevel(uint8_t channel) {
  int pin = RX_PINS[channel];
  if (pin < 32) return (GPIO.in >> pin) & 1U;
  return (GPIO.in1.val >> (pin - 32)) & 1U;
}

void IRAM_ATTR rawEdgeIsr(void *argument) {
  uint8_t channel = static_cast<uint8_t>(reinterpret_cast<uintptr_t>(argument));
  uint16_t head = rawIsrHeads[channel];
  uint16_t next = (head + 1) % RAW_ISR_BUFFER_CAPACITY;
  if (next == rawIsrTails[channel]) {
    ++rawInputOverflowCounts[channel];
    return;
  }
  RawIsrSample &sample = rawIsrBuffers[channel][head];
  sample.cycles = ESP.getCycleCount();
  sample.microsecondsAndLevel = (micros() & 0x7FFFFFFFUL) |
                                (static_cast<uint32_t>(rawPinLevel(channel)) << 31);
  rawIsrHeads[channel] = next;
}

void commitRawPending(uint8_t channel) {
  RawPendingCapture &source = rawPending[channel];
  if (!source.pulseCount) return;
  RawEdgeEvent &event = rawEvents[rawEventHead];
  event.sequence = nextRawSequence++;
  event.microseconds = source.startedAt;
  event.channel = channel + 1;
  event.pulseCount = source.pulseCount;
  memcpy(event.pulses, source.pulses, source.pulseCount * sizeof(uint32_t));
  source.pulseCount = 0;
  rawEventHead = (rawEventHead + 1) % RAW_EVENT_CAPACITY;
  if (rawEventCount < RAW_EVENT_CAPACITY) ++rawEventCount;
  else ++rawEvictedCount;
}

void appendRawPulse(uint8_t channel, uint8_t level, uint32_t durationTicks,
                    uint32_t startedAt) {
  if (!durationTicks) return;
  RawPendingCapture &item = rawPending[channel];
  if (!item.pulseCount) item.startedAt = startedAt;
  item.pulses[item.pulseCount++] =
      (static_cast<uint32_t>(level) << 31) | (durationTicks & 0x7FFFFFFFUL);
  if (item.pulseCount == RAW_PULSE_CAPACITY) commitRawPending(channel);
}

void setupRawCapture() {
  uint32_t nowCycles = ESP.getCycleCount();
  uint32_t nowUs = micros() & 0x7FFFFFFFUL;
  for (uint8_t channel = 0; channel < CHANNEL_COUNT; ++channel) {
    rawLastCycles[channel] = nowCycles;
    rawLastMicroseconds[channel] = nowUs;
    rawLastLevels[channel] = rawPinLevel(channel);
    attachInterruptArg(RX_PINS[channel], rawEdgeIsr,
                       reinterpret_cast<void *>(static_cast<uintptr_t>(channel)), CHANGE);
  }
}

void captureRawEdges() {
  const uint32_t cyclesPerTick = max(1UL, static_cast<uint32_t>(getCpuFrequencyMhz()) / 4UL);
  uint32_t nowUs = micros() & 0x7FFFFFFFUL;
  for (uint8_t channel = 0; channel < CHANNEL_COUNT; ++channel) {
    while (rawIsrTails[channel] != rawIsrHeads[channel]) {
      uint16_t tail = rawIsrTails[channel];
      RawIsrSample sample = rawIsrBuffers[channel][tail];
      rawIsrTails[channel] = (tail + 1) % RAW_ISR_BUFFER_CAPACITY;

      uint8_t newLevel = sample.microsecondsAndLevel >> 31;
      uint32_t sampleUs = sample.microsecondsAndLevel & 0x7FFFFFFFUL;
      uint32_t deltaUs = (sampleUs - rawLastMicroseconds[channel]) & 0x7FFFFFFFUL;
      uint32_t deltaCycles = sample.cycles - rawLastCycles[channel];
      uint32_t durationTicks;
      if (deltaUs > 20000UL) {
        uint64_t longTicks = static_cast<uint64_t>(deltaUs) * 4ULL;
        durationTicks = static_cast<uint32_t>(min(longTicks, 0x7FFFFFFFULL));
      } else {
        durationTicks = (deltaCycles + cyclesPerTick / 2) / cyclesPerTick;
      }
      uint32_t startedAt = (sampleUs - deltaUs) & 0x7FFFFFFFUL;
      appendRawPulse(channel, rawLastLevels[channel], durationTicks, startedAt);
      rawLastCycles[channel] = sample.cycles;
      rawLastMicroseconds[channel] = sampleUs;
      rawLastLevels[channel] = newLevel;
    }
    uint32_t idleUs = (nowUs - rawLastMicroseconds[channel]) & 0x7FFFFFFFUL;
    if (rawPending[channel].pulseCount && idleUs >= 10000UL) commitRawPending(channel);
  }
}

String jsonEscaped(const String &value) {
  String out;
  out.reserve(value.length() + 8);
  for (size_t i = 0; i < value.length(); ++i) {
    char c = value[i];
    if (c == '\\' || c == '"') out += '\\';
    if (static_cast<uint8_t>(c) >= 32) out += c;
  }
  return out;
}

String configJson() {
  String result = "[";
  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    if (i) result += ',';
    result += "{\"channel\":" + String(i + 1) + ",\"pin\":" + String(RX_PINS[i]) +
              ",\"name\":\"" + jsonEscaped(channelNames[i]) + "\",\"baud\":" +
              String(configs[i].baud) + ",\"format\":\"" + configs[i].formatName + "\"}";
  }
  result += ']';
  return result;
}

void handleRawData() {
  uint32_t after = server.hasArg("after") ? strtoul(server.arg("after").c_str(), nullptr, 10) : 0;
  bool latestOnly = server.hasArg("latest");
  uint32_t inputOverflow = 0;
  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) inputOverflow += rawInputOverflowCounts[i];
  String result;
  result.reserve(5000);
  result = "{\"tickNs\":" + String(RAW_TICK_NS) + ",\"latest\":" + String(nextRawSequence - 1) +
           ",\"evicted\":" + String(rawEvictedCount) +
           ",\"inputOverflow\":" + String(inputOverflow) + ",\"inputOverflowChannels\":[";
  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    if (i) result += ',';
    result += String(rawInputOverflowCounts[i]);
  }
  result += "],\"events\":[";
  bool first = true;
  size_t start = (rawEventHead + RAW_EVENT_CAPACITY - rawEventCount) % RAW_EVENT_CAPACITY;
  for (size_t i = 0; i < rawEventCount; ++i) {
    const RawEdgeEvent &event = rawEvents[(start + i) % RAW_EVENT_CAPACITY];
    if (latestOnly) continue;
    if (event.sequence <= after) continue;
    if (!first) result += ',';
    first = false;
    result += "{\"seq\":" + String(event.sequence) + ",\"us\":" + String(event.microseconds) +
              ",\"ch\":" + String(event.channel) + ",\"raw\":\"";
    char pulseHex[9];
    for (uint8_t j = 0; j < event.pulseCount; ++j) {
      snprintf(pulseHex, sizeof(pulseHex), "%08lX", static_cast<unsigned long>(event.pulses[j]));
      result += pulseHex;
    }
    result += "\"}";
    if (result.length() > 12000) break;
  }
  result += "]}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", result);
}

void appendEscapedAscii(String &out, const CaptureEvent &event) {
  for (uint8_t i = 0; i < event.length; ++i) {
    char c = static_cast<char>(event.data[i]);
    if (c >= 32 && c <= 126) {
      if (c == '\\' || c == '"') out += '\\';
      out += c;
    } else out += '.';
  }
}

void handleData() {
  uint32_t after = server.hasArg("after") ? strtoul(server.arg("after").c_str(), nullptr, 10) : 0;
  bool latestOnly = server.hasArg("latest");
  String result;
  result.reserve(5000);
  result = "{\"softOverflow\":" + String(softwareOverflowCount) + ",\"latest\":" +
           String(nextSequence - 1) + ",\"events\":[";
  bool first = true;
  size_t start = (eventHead + EVENT_CAPACITY - eventCount) % EVENT_CAPACITY;
  for (size_t i = 0; i < eventCount; ++i) {
    const CaptureEvent &event = events[(start + i) % EVENT_CAPACITY];
    if (latestOnly) continue;
    if (event.sequence <= after) continue;
    if (!first) result += ',';
    first = false;
    result += "{\"seq\":" + String(event.sequence) + ",\"us\":" + String(event.microseconds) + ",\"ch\":" + String(event.channel) + ",\"hex\":\"";
    char byteHex[4];
    for (uint8_t j = 0; j < event.length; ++j) {
      snprintf(byteHex, sizeof(byteHex), "%02X", event.data[j]);
      if (j) result += ' ';
      result += byteHex;
    }
    result += "\",\"ascii\":\"";
    appendEscapedAscii(result, event);
    result += "\"}";
    if (result.length() > 12000) break;
  }
  result += "]}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", result);
}

void handleConfigPost() {
  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    String nameArg = "n" + String(i);
    String baudArg = "b" + String(i);
    String formatArg = "f" + String(i);
    String name = server.hasArg(nameArg) ? server.arg(nameArg) : channelNames[i];
    name.trim();
    if (name.length() > 24) {
      server.send(400, "text/plain", "Nazwa kanalu jest za dluga");
      return;
    }
    uint32_t baud = server.hasArg(baudArg) ? strtoul(server.arg(baudArg).c_str(), nullptr, 10) : configs[i].baud;
    if (!validBaud(baud)) {
      server.send(400, "text/plain", "Nieprawidlowa predkosc");
      return;
    }
    String format = server.hasArg(formatArg) ? server.arg(formatArg) : configs[i].formatName;
    configs[i].baud = baud;
    configs[i].formatName = normalizedFormat(format);
    configs[i].serialConfig = serialConfigFromName(configs[i].formatName);
    channelNames[i] = name;
    preferences.putString(("n" + String(i)).c_str(), channelNames[i]);
    preferences.putUInt(("b" + String(i)).c_str(), configs[i].baud);
    preferences.putString(("f" + String(i)).c_str(), configs[i].formatName);
    beginChannel(i);
  }
  server.send(200, "application/json", configJson());
}

void setupWebServer() {
  server.on("/", HTTP_GET, [] { server.send_P(200, "text/html; charset=utf-8", INDEX_HTML); });
  server.on("/api/config", HTTP_GET, [] { server.send(200, "application/json", configJson()); });
  server.on("/api/config", HTTP_POST, handleConfigPost);
  server.on("/api/data", HTTP_GET, handleData);
  server.on("/api/raw", HTTP_GET, handleRawData);
  server.on("/update", HTTP_GET, [] {
    if (!server.authenticate("admin", AP_PASSWORD)) return server.requestAuthentication();
    server.send_P(200, "text/html; charset=utf-8", UPDATE_HTML);
  });
  server.on("/api/update", HTTP_POST, [] {
    if (!server.authenticate("admin", AP_PASSWORD)) return server.requestAuthentication();
    bool success = httpUpdateAuthorized && !Update.hasError();
    server.send(200, "text/plain; charset=utf-8", success ? "Aktualizacja zakonczona. ESP32 uruchamia sie ponownie." : "Aktualizacja nie powiodla sie.");
    httpUpdateAuthorized = false;
    if (success) restartAt = millis() + 1000;
  }, [] {
    HTTPUpload &upload = server.upload();
    if (upload.status == UPLOAD_FILE_START) {
      httpUpdateAuthorized = server.authenticate("admin", AP_PASSWORD);
      if (httpUpdateAuthorized) Update.begin(UPDATE_SIZE_UNKNOWN);
    } else if (upload.status == UPLOAD_FILE_WRITE && httpUpdateAuthorized) {
      if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) httpUpdateAuthorized = false;
    } else if (upload.status == UPLOAD_FILE_END && httpUpdateAuthorized) {
      if (!Update.end(true)) httpUpdateAuthorized = false;
    } else if (upload.status == UPLOAD_FILE_ABORTED) {
      Update.abort();
      httpUpdateAuthorized = false;
    }
  });
  server.on("/api/network", HTTP_GET, [] {
    String ssid = preferences.getString("wifi_ssid", DEFAULT_WIFI_SSID);
    String json = "{\"ssid\":\"" + ssid + "\",\"connected\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false") +
                  ",\"ip\":\"" + WiFi.localIP().toString() + "\",\"apIp\":\"" + WiFi.softAPIP().toString() +
                  "\",\"rssi\":" + String(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0) + ",\"host\":\"" + HOSTNAME + "\"}";
    server.send(200, "application/json", json);
  });
  server.on("/api/network", HTTP_POST, [] {
    String ssid = server.arg("ssid");
    String password = server.arg("password");
    ssid.trim();
    if (ssid.isEmpty() || ssid.length() > 32 || password.length() > 63) {
      server.send(400, "text/plain", "Nieprawidlowa nazwa sieci lub haslo");
      return;
    }
    preferences.putString("wifi_ssid", ssid);
    if (!password.isEmpty()) preferences.putString("wifi_pass", password);
    server.send(200, "application/json", "{\"restart\":true}");
    restartAt = millis() + 700;
  });
  server.onNotFound([] { server.send(404, "text/plain", "404"); });
  server.begin();
}

void setupNetwork() {
  String ssid = preferences.getString("wifi_ssid", DEFAULT_WIFI_SSID);
  String password = preferences.getString("wifi_pass", DEFAULT_WIFI_PASSWORD);
  WiFi.mode(WIFI_AP_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  WiFi.begin(ssid.c_str(), password.c_str());

  uint32_t deadline = millis() + 15000;
  while (WiFi.status() != WL_CONNECTED && static_cast<int32_t>(deadline - millis()) > 0) delay(100);

  ArduinoOTA.setHostname(HOSTNAME);
  ArduinoOTA.setPassword(AP_PASSWORD);
  ArduinoOTA.begin();
}

}  // namespace

void setup() {
  preferences.begin("uartlogger", false);
  for (uint8_t i = 0; i < CHANNEL_COUNT; ++i) {
    channelNames[i] = preferences.getString(("n" + String(i)).c_str(), "CH" + String(i + 1));
    configs[i].baud = preferences.getUInt(("b" + String(i)).c_str(), 9600);
    String format = preferences.getString(("f" + String(i)).c_str(), "8N1");
    configs[i].formatName = normalizedFormat(format);
    configs[i].serialConfig = serialConfigFromName(configs[i].formatName);
    beginChannel(i);
  }
  setupNetwork();
  setupWebServer();
  setupRawCapture();
}

void loop() {
  captureUarts();
  captureRawEdges();
  server.handleClient();
  ArduinoOTA.handle();
  if (restartAt && static_cast<int32_t>(millis() - restartAt) >= 0) ESP.restart();
  delay(1);
}
