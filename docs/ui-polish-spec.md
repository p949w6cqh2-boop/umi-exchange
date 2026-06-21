

```markdown
# UMI UI Polish Spec - "Parish Hall Bulletin Board"

## Goal
Eliminate the "bland/Squarespace" aesthetic. Move to a highly glanceable, tactile, and bespoke design. People look at websites, they don't read them.

## 1. Design System (`static/css/input.css`)
Update `@layer base` and `@layer components` with the following:

```css
@layer base {
  html { scroll-behavior: smooth; }
  body {
    background-color: #FDFBF7;
    background-image: radial-gradient(#EDE8E0 1px, transparent 1px);
    background-size: 24px 24px;
    color: #2C2A29;
    font-family: 'Open Sans', system-ui, sans-serif;
  }
  h1, h2, h3, h4, h5 {
    font-family: 'Lora', 'Georgia', serif;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  a { @apply transition-colors duration-200; }
}

@layer components {
  .card-parish { @apply relative bg-white rounded-xl shadow-sm border border-[#EDE8E0] p-5 transition-all duration-300 ease-in-out hover:shadow-lg hover:-translate-y-1; }
  .card-need { @apply card-parish border-l-[6px] border-l-[#2B5E2B]; }
  .card-offer { @apply card-parish border-l-[6px] border-l-[#C49A3C]; }
  .btn-parish { @apply inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full bg-[#2B5E2B] text-white font-semibold tracking-wide shadow-md hover:bg-[#244F24] hover:shadow-lg active:scale-95 transition-all duration-200; }
  .btn-parish-gold { @apply inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full bg-[#C49A3C] text-[#2C2A29] font-semibold tracking-wide shadow-md hover:bg-[#B08832] hover:shadow-lg active:scale-95 transition-all duration-200; }
  .btn-parish-outline { @apply inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full bg-transparent border-2 border-[#2B5E2B] text-[#2B5E2B] font-semibold tracking-wide hover:bg-[#2B5E2B] hover:text-white active:scale-95 transition-all duration-200; }
  .pill-category { @apply inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-[#F3F0E8] text-[#5C5248]; }
  .badge-urgent { @apply inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-700; }
  .input-parish { @apply w-full px-4 py-3 rounded-lg bg-[#FDFBF7] border-2 border-[#EDE8E0] text-[#2C2A29] placeholder-[#A39B92] transition-all duration-200 focus:outline-none focus:border-[#2B5E2B] focus:ring-2 focus:ring-[#2B5E2B]/20; }
  .label-parish { @apply block text-sm font-semibold text-[#5C5248] mb-2; }
  .modal-panel { @apply bg-white w-full max-w-lg rounded-2xl shadow-2xl border border-[#EDE8E0] overflow-hidden; }
  .timeline-step { @apply flex items-center text-sm font-semibold; }
  .timeline-dot { @apply w-8 h-8 rounded-full flex items-center justify-center mr-3 border-2; }
  .timeline-active { @apply bg-[#2B5E2B] border-[#2B5E2B] text-white; }
  .timeline-incomplete { @apply bg-[#F3F0E8] border-[#EDE8E0] text-[#A39B92]; }
}
```

## 2. Template Updates
Apply the tactile classes to the following templates (use the exact HTML structure provided in the chat history, condensed here for the agent):
- `templates/base.html`: Translucent blurred header (`backdrop-blur-md bg-[#FDFBF7]/80`), dark warm footer.
- `templates/feed.html`: Responsive grid `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6`.
- `templates/components/_need_card.html`: Use `.card-need`, include urgency ping SVG, bold serif title.
- `templates/components/_offer_card.html`: Use `.card-offer`, include gold dot SVG, bold serif title.
- `templates/components/_empty_state.html`: Large inline SVG illustration, warm copy, `.btn-parish` and `.btn-parish-gold`.
- `templates/_need_detail.html`: Modal panel using Alpine.js for close, green header, `.btn-parish` for action.
- `templates/_match_timeline.html`: Visual timeline using `.timeline-step`, `.timeline-dot`, `.timeline-active`.
- `templates/_need_form.html`: Tactile form using `.input-parish`, `.label-parish`, and `.btn-parish`.

## 3. Execution Rules
- DO NOT hand-edit `static/css/output.css`.
- DO NOT change any view logic, URLs, or models. Presentation only.
- Run `npx tailwindcss@3.4.14 -i static/css/input.css -o static/css/output.css --minify` at the end.
```

### Step 3: Run the Local Agent Command
Now, open your local Claude Code in the `umi-exchange` directory and run this exact prompt:

```text
Read the file at docs/ui-polish-spec.md. 
Execute the instructions in that file: update static/css/input.css, and update/refactor the specified HTML templates. 
Follow the Keyring trust model: draft the changes locally, do not push to main. 
When finished, run the Tailwind recompile command and run `pytest` to ensure no template rendering errors occurred. Report back what you changed.
```
