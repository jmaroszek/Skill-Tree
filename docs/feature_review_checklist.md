# Feature Review Checklist

Every feature in Skill Tree, visible and hidden, and what to check in each. Work through it top to bottom, or jump to a section. Each item has an ID, so you can refer to it later ("ED-14 fails").

Three questions apply to every item:

1. **Does it work?** It does what the item says.
2. **Is it robust?** Try it twice in a row, fast, with odd input, and from another tab.
3. **Is it your vision?** It should work the way you want, not just the way it was built. Note anything that feels wrong even if it passes.

Before you start, read [Review Status](#review-status). It lists what was already driven and fixed, and the decisions waiting for you.

## Setup

Run the sandbox, never production:

```bash
python app.py --sandbox --port 8051 --dev --no-browser
```

```bash
C:\Users\jonah\Documents\Code\Terminal\Batch\skill_tree_sandbox.bat
```

- Many items below change data. Choose Settings → App → **Back up now** before you start, and restore that backup when you finish.
- First-launch items need an empty data folder. Set `SKILLTREE_HOME` to a new folder for that server only.
- Items marked (desktop) need the Electron window. Everything else also works in a browser.

## Review Status

A first pass ran on 2026-11-01, starting from commit 3c07a51. It read the code behind every item, then drove the app in a real browser, on throwaway copies of the sandbox data. It never touched your production data.

- [Fixed](#fixed-in-the-first-pass) lists the problems that are now gone. Each has tests, and each was checked again in the browser. Start with those items, since they changed.
- [Decisions for you](#decisions-for-you) lists what might have been a problem or your design, and what you decided on each.
- [What the first pass couldn't check](#what-the-first-pass-couldnt-check) lists where your eyes matter most: the desktop app, how things feel, and whether it's what you want.

---

# 1. Launch and First Run

## Startup

- [ ] ST-1. The window title says "Skill Tree (Sandbox)" in the sandbox and "Skill Tree" in production.
- [ ] ST-2. A "Getting ready…" cover shows first, then lifts on its own. Nothing can be clicked until it lifts.
- [ ] ST-3. The app opens on Home, with no flash of an unfinished layout.
- [ ] ST-4. Filters open cleared at every launch, whatever you set last time.
- [ ] ST-5. Events due while the app was closed announce themselves at launch, and their nodes are awake.

## Welcome

Use an empty data folder for these.

- [ ] ST-6. The welcome dialog opens on a first launch only. Escape and clicking outside don't close it.
- [ ] ST-7. **Use the suggested contexts** closes it, and the context pickers offer the suggested list.
- [ ] ST-8. **Start with just General** reloads the page, and General is the only context.
- [ ] ST-9. **Import a graph…** opens Settings on the App page.
- [ ] ST-10. The welcome never returns once answered. It also never appears for a graph that already has nodes.

## Getting Started

- [ ] ST-11. The card on Home lists four steps: add a goal, connect work to it, pick something for Now, mark something Done.
- [ ] ST-12. Each step ticks itself off as you do it, however you do it.
- [ ] ST-13. A ticked step stays ticked, even when you later undo what ticked it.
- [ ] ST-14. The card's wording matches the app's menus and buttons.
- [ ] ST-15. **Hide** removes it for good, across restarts. It also goes away once every step is done.

## Refusing to start

Try these on copies of a database in a throwaway data folder. Each should leave the file untouched.

- [ ] ST-16. A database saved by a newer version says to install the newer version.
- [ ] ST-17. A database saved by an older version says this version doesn't upgrade it.
- [ ] ST-18. A damaged file offers to restore the newest good backup (desktop). Accepting keeps the damaged file beside it.
- [ ] ST-19. With no good backup, nothing changes and the message says where backups are.
- [ ] ST-20. A file held by another program says to close that program. It never offers a restore.
- [ ] ST-21. A read-only file or folder says so.
- [ ] ST-22. A second launch hands over to the running one rather than starting another server. (desktop) The existing window comes forward.

---

# 2. App Shell

## Toolbar and tabs

- [ ] SH-1. The tabs read Home, Nodes, Details, Events, Analyze. Each opens quickly and keeps its state when you return.
- [ ] SH-2. The left icons open the Node Editor, Goals and Events. They share one slot: opening one closes the other two.
- [ ] SH-3. Clicking an open sidebar's icon closes it. Its X does too.
- [ ] SH-4. Filters opens on the right and can stay open beside any left sidebar.
- [ ] SH-5. The funnel icon fills in while a filter is narrowing the app. Show Done and Show Dormant don't fill it.
- [ ] SH-6. The journal icon opens Reflection. It disappears when Reflection is turned off in Settings.
- [ ] SH-7. Clear Focus appears only while a focus view is on.

## Messages and errors

- [ ] SH-8. A save's message appears at the bottom of the editor and fades after about five seconds.
- [ ] SH-9. A message starting with "Error:" opens the Validation Error dialog instead.
- [ ] SH-10. An unexpected failure opens "Something went wrong", which names the log folder. It never fails silently.
- [ ] SH-11. Toasts (Now cap, Reflection) sit below the toolbar, above menus, and dismiss themselves.

## Tooltips

- [ ] SH-12. Tooltips open on mouse hover only, after a short pause. Keyboard focus never opens one.
- [ ] SH-13. Moving between neighboring toolbar buttons hands over without the pause.
- [ ] SH-14. No tooltip sticks after the pointer leaves, a click, a tab switch or a menu opening.
- [ ] SH-15. A tooltip never opens by itself when something slides under a still pointer.
- [ ] SH-16. A disabled Save explains itself on hover. An enabled Save shows nothing.
- [ ] SH-17. Truncated names show their full text on hover. Names that fit show nothing.

## Small behaviors

- [ ] SH-18. The mouse wheel over a number field doesn't change its value.
- [ ] SH-19. The wheel scrolls sideways over Now cards and Milestone tiles.
- [ ] SH-20. Panel dividers on Details and Events drag, respect a minimum size, and work from the keyboard.
- [ ] SH-21. At the smallest window (900×600), nothing important is cut off or overlapping.
- [ ] SH-22. On your 4K screen, nothing looks stranded or tiny.
- [ ] SH-23. Descriptions can be selected and copied. Buttons and rows don't select as you click.
- [ ] SH-24. Every icon-only button has a tooltip that names it.
- [ ] SH-25. The left sidebars sit on top of Home rather than moving it, so they can hide the first Now card and the names in Next. Set aside for its own pass.

---

# 3. Node Editor

## Opening and closing

- [ ] ED-1. The toolbar icon opens the editor showing the last loaded node, or a blank form.
- [ ] ED-2. The **+** in the header starts a blank form. It asks first if there are unsaved edits.
- [ ] ED-3. The header stays in view as the form scrolls, and so do Delete, Revert and Save.
- [ ] ED-4. A new form scrolls to the top.
- [ ] ED-5. Clicking a node on the Nodes canvas loads it, even with the editor closed, without opening it. Unsaved edits left behind another sidebar stay as they are (ED-105).
- [ ] ED-6. Clicking empty canvas starts a blank form when clean, and asks when there are unsaved edits. Its Save or Discard closes the editor.

## Search and Locate

- [ ] ED-7. Search suggests names and aliases as you type. An alias shows as "alias → node".
- [ ] ED-8. Picking a name loads that node and opens the editor. Picking an alias loads the node it belongs to.
- [ ] ED-9. Clearing Search starts a blank form, and asks first if there are unsaved edits.
- [ ] ED-10. The crosshair is disabled with no node loaded.
- [ ] ED-11. Locate pulses the node on the open canvas, panning to it if offscreen.
- [ ] ED-12. On Details or Events, a node not on that canvas takes you to the Nodes canvas and pulses it there.
- [ ] ED-13. From Home or Analyze, Locate moves to Nodes and pulses it.
- [ ] ED-14. A node hidden by filters opens "is hidden on the Nodes canvas". Its button (Show Done, Show Dormant or Clear Filters) reveals the node and then pulses it. Dismiss changes nothing.
- [ ] ED-15. A dormant node's Locate goes to its event's canvas.

## Name, aliases, type, description, context

- [ ] ED-16. Leaving the Name field on a near duplicate shows "Possible duplicate", ignoring case and connector words like "the" and "of". It fades after a few seconds.
- [ ] ED-17. The warning appears every time you leave the field on a duplicate, not only the first.
- [ ] ED-18. Saving an exact duplicate name, in any case, is refused and names the other node. The form stays open with your input.
- [ ] ED-19. A name over 200 characters, or with a tab or newline, is refused with a reason.
- [ ] ED-20. Name formatting applies on save: as typed, Title Case or Sentence case. The field then shows the saved form.
- [ ] ED-21. The **+** beside Name reveals an alias row. Further clicks add rows. Removing the last row hides the section. A loaded node's aliases show by themselves, and the section closes on a node with none.
- [ ] ED-22. Aliases save, reload, and find the node from Search and from the Filters search.
- [ ] ED-23. An alias owned by another node is refused, and the save changes nothing.
- [ ] ED-24. An alias can't match another node's name, and a name can't match another node's alias. Each is refused and names the other node.
- [ ] ED-25. Type starts unselected on a new node. Saving without one is refused.
- [ ] ED-26. The Type label's hover lists all five types with one line each.
- [ ] ED-27. Description is a resizable box. Line breaks survive and show on Home and Details.
- [ ] ED-28. Context is required. Saving without one is refused with a reason.
- [ ] ED-29. The context picker opens, searches, and offers "No subcontext". Changing context clears a subcontext that doesn't belong.
- [ ] ED-30. Dropdown order follows Settings → Contexts (defined or alphabetical).

## Status

- [ ] ED-31. Now waits for Save like every other field. Flipping it writes nothing, Revert undoes it, and leaving asks first.
- [ ] ED-32. Now refuses past the cap: the switch bounces back at once and the toast explains. A list that fills up before the Save doesn't refuse the save, and the message says Now wasn't added.
- [ ] ED-33. Done waits for Save. A node with unfinished hard prerequisites is refused and names them.
- [ ] ED-34. A Goal or Milestone can be marked Done with unfinished prerequisites.
- [ ] ED-35. Un-marking Done with no Done nodes after it just reopens. With some, a dialog lists them first. Cancel leaves the node Done with the switch back on.
- [ ] ED-36. Marking Done opens the Reflection prompt once, not again on a re-save.
- [ ] ED-37. Saving a Done node with a new Hard prerequisite that isn't Done lists what would reopen. Save goes ahead; Cancel keeps the form, unsaved.
- [ ] ED-38. An excluded node shows the note about being excluded from reflection, and the note says where to restore it.

## Dormant

- [ ] ED-39. Dormant writes nothing until Save. While it is on, Now and Done hide. While either of those is on, Dormant hides.
- [ ] ED-40. Turning Dormant on shows Event. Saving with no event is refused.
- [ ] ED-41. **New event…** asks for a name. Saving creates a Manual event and puts the node to sleep in it. A duplicate event name is refused.
- [ ] ED-42. Picking an event shows Wake settings: Delay and Add to Now.
- [ ] ED-43. Delay reveals a value and a unit. A negative delay, or one over 100 years, is refused.
- [ ] ED-44. Turning Dormant off on a sleeping node warns what Save will do. Save wakes it and removes it from its event.
- [ ] ED-45. Choosing another event and saving moves the node there.
- [ ] ED-46. After the event fires, a delayed node shows a wake date instead of a delay. Clearing the date is refused.
- [ ] ED-47. A node can't sleep in an event it triggers. The message says why.
- [ ] ED-48. A node its event already woke can sleep again, under a Pending event. The new event replaces the old one, which no longer lists it.
- [ ] ED-49. A node that wakes while its editor is open saves fine, stays awake, and the message says so.

## Ratings

- [ ] ED-50. Value, Interest and Effort are 1 to 10 sliders.
- [ ] ED-51. The info icon opens the Ratings Reference, a floating panel that drags by its header and resizes.
- [ ] ED-52. Its pencil opens an editable table and steps aside. It comes back where it was after Save or Cancel. Save changes the definitions, Cancel changes nothing, and definitions survive a restart.
- [ ] ED-53. Inherit hides Value and Interest. Effort stays while the node has its own hours.
- [ ] ED-54. Inherit on a Milestone is locked on, and trying to clear it explains why.
- [ ] ED-55. A Goal has no Effort slider ("Derived from subtasks").
- [ ] ED-56. Inherited time also hides Effort.

## Time

- [ ] ED-57. A new node's estimate is blank. Save is disabled until there is one, and hovering says why. That includes the form a fresh page opens with.
- [ ] ED-58. Valid patterns: Expected alone; Lower and Upper; all three in order. Every other pattern disables Save with a reason. The message appears once you leave the section.
- [ ] ED-59. The unit dropdown converts the numbers in place. Switching units and back doesn't lose or round away an estimate.
- [ ] ED-60. Hour equivalents show under each field when the setting is on, and follow your hour rates.
- [ ] ED-61. The heading's hover shows your rates, and updates after you change them in Settings.
- [ ] ED-62. An untouched estimate keeps its stored hours through a save, even after you change the hour rates in Settings.
- [ ] ED-63. Inherit hides the fields and scores the node at its children's time. Goal and Milestone lock it on, and explain why if you try to clear it.
- [ ] ED-64. Changing a Goal or Milestone to Action or Resource gives it back its own estimate. A Learn keeps Inherit with a note.
- [ ] ED-65. Habit shows Calendar duration, Minutes per session and days. Inherit and Habit can't both be on.
- [ ] ED-66. The habit preview line shows total hours and the cadence, and updates as you type.
- [ ] ED-67. A habit with no duration, a bad bracket or no days disables Save, and says why.
- [ ] ED-68. Reloading a habit restores its duration, minutes and days.

## Relationships

- [ ] ED-69. Needs and Supports each have Hard and Soft pickers, and Helps has one. Every picker includes dormant nodes.
- [ ] ED-70. A node can't pick itself.
- [ ] ED-71. Each label's hover explains direction. Needs lists what comes first; Supports lists what this unlocks.
- [ ] ED-72. The same other node in two directional pickers is refused with a clear message.
- [ ] ED-73. A choice that would close a cycle is refused and the whole save rolls back.
- [ ] ED-74. A Helps link can sit alongside a Hard or Soft link on the same pair.
- [ ] ED-75. A Hard prerequisite that isn't Done turns the node Blocked as soon as you save.
- [ ] ED-76. Changing links from the canvas menu while the editor is open updates its untouched pickers. An edited picker keeps your edits on top.

## Resources

- [ ] ED-77. One field per resource kind in Settings, with the kind's name above it.
- [ ] ED-78. **+** adds a row. **×** removes one, and appears only with two or more rows.
- [ ] ED-79. A web URL opens in your browser. A bare domain does too.
- [ ] ED-80. The folder icon opens a file picker (native in the desktop app). The chosen path saves relative to the kind's root folder when inside it.
- [ ] ED-81. A note inside an Obsidian vault opens in Obsidian. Other files open in their default app.
- [ ] ED-82. A program, script, installer or shortcut asks before opening. So does an unfamiliar link scheme and a file on another computer.
- [ ] ED-83. A missing file or unset root opens the error dialog, which says what's wrong. From the node menu it's a small alert.
- [ ] ED-84. The open button appears once the field has text.
- [ ] ED-85. Links survive a rename.

## Save, Revert, Delete

- [ ] ED-86. Save keeps the editor open, selects the node on the canvas, and shows "Added node" or "Updated node".
- [ ] ED-87. After a save, the form counts as clean. Closing asks nothing.
- [ ] ED-88. Saving with a blank name asks for a name, whatever else you filled in, and the form stays. A loaded node with its name cleared gets the same answer.
- [ ] ED-89. Rename keeps every link, alias, resource, event, priority rank and history row.
- [ ] ED-90. Revert reloads the saved node and says so. It is disabled for an unsaved node.
- [ ] ED-91. Delete asks first, naming the loaded node even if the Name field has changed.
- [ ] ED-92. On an unsaved form, Delete says it just closes the editor.
- [ ] ED-93. Deleting a node's prerequisite unblocks what it was blocking.
- [ ] ED-94. Ctrl+S saves when focus is in the editor.

## Unsaved changes

- [ ] ED-95. Any changed field, then Close, the toolbar icon, a canvas click, Edit on another node, or Search: the dialog asks, and can't be dismissed with Escape or a click outside.
- [ ] ED-96. **Edit** returns you to the form with nothing lost.
- [ ] ED-97. **Discard** goes where you were heading.
- [ ] ED-98. **Save** goes where you were heading only if the save succeeds. A refused save keeps the form and shows why.
- [ ] ED-99. Loading a node and changing nothing never counts as a change.
- [ ] ED-104. Opening Goals or Events slides the editor away with your unsaved edits, without asking. Reopening it brings them back.
- [ ] ED-105. While edits wait there, a canvas click neither asks nor replaces them, and an empty click doesn't blank them. Edit on another node, the Goals **+** and the other **+** menus ask first, with the editor showing what's at stake.
- [ ] ED-106. The form a fresh page opens with counts too. Type into it before loading anything, and closing asks.

## The + on other surfaces

- [ ] ED-100. The Goals sidebar's **+** opens a blank form with type Goal. It never changes the node already loaded, and asks first if there are unsaved edits.
- [ ] ED-101. Details' **+ → New node** opens a blank form with the selected node under Supports → Hard.
- [ ] ED-102. Events' **+ → New node** opens a blank form already Dormant under that event.
- [ ] ED-103. A bridge's Create opens a blank form with both links filled in.

---

# 4. Home

## Now

- [ ] HM-1. The Now section appears only with Now nodes, and each card shows a type bar, name, time and context.
- [ ] HM-2. Drag cards to reorder. The order survives a restart.
- [ ] HM-3. A click selects a card and shows its description beside the table.
- [ ] HM-4. A sixth node is refused with a toast. The cap comes from Settings, and the toast states the current cap.
- [ ] HM-5. Marking a Now node Done or Dormant takes it off the list.
- [ ] HM-6. A Now node leaves the Next table, and its peers' numbers don't get worse for it.
- [ ] HM-7. Lowering the cap below the current count keeps the existing cards and refuses new ones.

## Blocked Now nodes

- [ ] HM-8. A blocked Now node, or a Goal, pins up to three steps at the top of Next.
- [ ] HM-9. Each pinned row has an arrow in place of a rank, and says "toward [target]".
- [ ] HM-10. The context line drops what the target already implies.
- [ ] HM-11. Pinned rows show their true score, ignore the filters, and don't use up the row count.
- [ ] HM-12. Ranks below still run 1, 2, 3. Finishing a step refreshes the list.

## Next

- [ ] HM-13. Rows show rank, name, context · subcontext, a colored bar with the score, time, three rating bars and one dot per resource kind.
- [ ] HM-14. Scores descend down the list, and the top is 100 with no filter on.
- [ ] HM-15. A filter never changes a node's number. The top bar can read under 100.
- [ ] HM-16. The bar's length is relative to the longest row shown.
- [ ] HM-17. Only Learn, Action and Resource nodes appear. Containers with inherited time don't.
- [ ] HM-18. Blocked, Done and dormant nodes never appear.
- [ ] HM-19. **+** and **−** change the row count, never below 1. The number can be typed over: Enter or clicking away applies it, and anything but a whole number from 1 to 999 puts the last one back. It reads as plain text until clicked, the buttons stay gray, and the count survives a restart.
- [ ] HM-20. A click selects a row and shows its description, without a server wait.
- [ ] HM-21. The panel also lists what the node supports and its synergy partners, best first, with a "more" control.
- [ ] HM-22. The selection survives a refresh while the row stays visible.
- [ ] HM-23. Hovering the rating bars names each value. Hovering a dot says whether that link is set.
- [ ] HM-24. The "Filtered" chip lists what's narrowing the list. Its × clears the filters.
- [ ] HM-25. Community and Orphans narrow Next, and show in its chip.
- [ ] HM-26. With "Show graph statistics" on, a caption shows the nodes left to do, the edges and the scoring time. It hides when content would sit under it.
- [ ] HM-27. Turning that setting off hides the caption without a restart. Its counts stay right after you add a node.

## Variety

- [ ] HM-28. Under Sage, a second task from one context reads about 5% lower, and from one subcontext about 15% lower.
- [ ] HM-29. Adding an unrelated node to a context doesn't lower other tasks' scores.

---

# 5. Menus, Links and Bridges

## Node menu

Check it on a Home row, a Now card, a goal card, and all three canvases.

- [ ] MN-1. The groups are: Edit; View Details and Explain; Open links; Set Priority; Now, Done and Add to Event; pair actions; Delete.
- [ ] MN-2. Edit opens the editor. From Nodes it stays on Nodes. Elsewhere it opens in place.
- [ ] MN-3. View Details jumps to Details on that node, including a dormant node from the Events canvas.
- [ ] MN-4. Explain opens the modal on any tab.
- [ ] MN-5. Open items list only kinds the node has a link in, named after the kind. Each opens the first link.
- [ ] MN-6. A risky link asks first here too.
- [ ] MN-7. Set Priority shows only for one unfinished Goal, with 1, 2, 3 and Clear.
- [ ] MN-8. Add to Now or Remove from Now is hidden for Done and dormant nodes.
- [ ] MN-9. Mark Done or Reopen is hidden for dormant nodes.
- [ ] MN-10. Mark Done on a Blocked node explains what it needs. It doesn't go through.
- [ ] MN-11. Add to Event opens the modal with the node chosen. On a Done or dormant node it's hidden. With a mixed selection the label counts only nodes that can join.
- [ ] MN-12. Delete asks, naming the node or the count.
- [ ] MN-13. With several selected, labels show the count: "Mark 3 Done", "Add 3 to Now", "Delete 3…".
- [ ] MN-14. A mixed selection acts sensibly: if any isn't Done, all become Done. If any isn't Now, all join Now up to the cap.
- [ ] MN-15. Right-clicking an unselected node acts on it alone.
- [ ] MN-16. The menu stays on screen near every window edge, and Escape or a click elsewhere closes it.
- [ ] MN-17. Set Priority's submenu opens on hover and from the keyboard.

## Linking two nodes

- [ ] MN-18. With exactly two selected, the menu adds Add Soft Link, Add Hard Link and Create Bridge.
- [ ] MN-19. The node picked first leads to the other. Ctrl-click and Shift-click both pick.
- [ ] MN-20. An existing link keeps its direction and takes the new strength. A Synergy stays as it is.
- [ ] MN-21. A link that would close a circle is refused, and says to pick the other way round.
- [ ] MN-22. A Hard link into a Done node asks first.

## Link menu

- [ ] MN-23. Right-clicking a link offers Insert Node Here, Make Soft or Make Hard, Reverse Direction and Remove Link.
- [ ] MN-24. A Synergy offers only Insert and Remove.
- [ ] MN-25. Make Hard blocks the target until the source is Done. Make Soft lifts it.
- [ ] MN-26. Reverse is refused when another route already runs that way, and says why.
- [ ] MN-27. Make Hard or Reverse that would reopen Done nodes lists them first. Cancel changes nothing.
- [ ] MN-28. Changing a link back doesn't re-mark nodes Done.
- [ ] MN-29. Remove asks nothing and takes effect at once.

## Bridges

- [ ] MN-30. Create Bridge opens with Start as the first pick. An existing link sets the order and type.
- [ ] MN-31. Swap reverses Start and End. Synergy hides Swap and relabels them Node.
- [ ] MN-32. The notice says when an existing link will be replaced, and that happens on saving the new node, not before.
- [ ] MN-33. Closing the editor without saving leaves the graph as it was.
- [ ] MN-34. A circular order disables Create and explains, until you swap.
- [ ] MN-35. A Hard bridge into a Done End asks on save.
- [ ] MN-36. Insert Node Here on a Synergy keeps the Synergy.
- [ ] MN-37. Editing the relationships away from the bridge before saving leaves the old link alone.

---

# 6. Explain

- [ ] EX-1. Explain opens from the menu and from Details, already filled in, without growing or jumping.
- [ ] EX-2. The header shows the node and where it ranks, or "Not ranked" and why. A Now node reads "Would rank…".
- [ ] EX-3. Top Contributors shows one bar per contributor, colored by Self, Hard, Soft or Synergy, with the legend below.
- [ ] EX-4. Bars show share of total value, and hovering shows ratings and the route.
- [ ] EX-5. The Show box changes the row count. It resets to 10 each time the modal opens.
- [ ] EX-6. Calculation details starts closed. Value shares add up to 100%.
- [ ] EX-7. Cost shows time and effort. Adjustments lists only what applies, each as a change.
- [ ] EX-8. The number matches Home, the subtask tables and, for a Goal, the Goals sidebar.
- [ ] EX-9. A Goal explains by the work left beneath it: ratings of the work left, credit for this goal, credit for other goals.
- [ ] EX-10. A dormant node says it's asleep and isn't ranked.
- [ ] EX-11. A Blocked or Done node says why it isn't ranked.
- [ ] EX-12. Selecting another node on Details with the modal open refills it, keeping your Show count.
- [ ] EX-13. Focus top n accepts 1 to 5, and says so otherwise.
- [ ] EX-14. Focus switches to Nodes, dims the rest and draws each route in its own color. Contributors on one line count as one route. It zooms toward the route, stops at natural size, and keeps the graph around it in view. Judge how far it zooms on your own graph.
- [ ] EX-15. A route's label sits at the contributor that started it.
- [ ] EX-16. Clear Focus returns the canvas to normal, and the view to where Focus found it.
- [ ] EX-17. Focus clears filters, from either button, so no part of a route is hidden.

---

# 7. Canvases

Check on Nodes, Details and Events unless an item names one.

## Drawing

- [ ] CV-1. Shape shows type, and color shows state. Done is green and Blocked is red.
- [ ] CV-2. A Goal stays yellow even with unfinished prerequisites.
- [ ] CV-3. Now nodes carry a pulsing outline in the Now color, with no pulse left behind when they leave Now.
- [ ] CV-4. Hard, Soft and Helps links are visually distinct, and arrows point from prerequisite to dependent.
- [ ] CV-5. Trigger nodes carry their badge, and dormant nodes look dormant.
- [ ] CV-6. The Nodes canvas shows "Preparing the graph…" on first visit, then appears laid out and framed, never piled in a corner.
- [ ] CV-7. A node count sits at the bottom left. On Details it names a depth limit.

## Gestures

- [ ] CV-8. Hover shows a tooltip with stats for that type. A Goal shows progress. A Done node shows "estimate → actual".
- [ ] CV-9. Click selects. Ctrl-click or Shift-click adds or removes. Clicking empty canvas clears.
- [ ] CV-10. Dragging a node moves it, and it stays. Dragging empty canvas box-selects.
- [ ] CV-11. Right-drag pans. The wheel zooms around the pointer.
- [ ] CV-12. Delete or Backspace on the focused Nodes canvas asks to delete the selection. It never fires from a form, a modal or another tab.
- [ ] CV-13. Clicking a link never selects it or clears the node selection.

## Graph Layout panel

- [ ] CV-14. The gear opens the panel. Its X, the gear and Escape close it. Clicking away does what you'd expect.
- [ ] CV-15. Animate glides layout changes. Off, they snap.
- [ ] CV-16. Edge Length, Gravity and Repulsion each visibly change the layout when released.
- [ ] CV-17. Settle untangles the graph, including while frozen.
- [ ] CV-18. Freeze stops re-layouts. A blue outline and a snowflake show it. Edits still apply, and new nodes appear near their neighbors.
- [ ] CV-19. While frozen, slider changes wait. Unfreezing applies them.
- [ ] CV-20. ↺ restores this canvas's defaults, and turns Freeze off.
- [ ] CV-21. A filter that swaps out more than half the nodes gets a fresh layout on its own. A small change glides.
- [ ] CV-22. Chains and trees don't collapse onto a line.

## Fullscreen

- [ ] CV-23. Fullscreen fills the window, with the panel, gear and menus still working.
- [ ] CV-24. Escape and the button both exit, and the view refits.
- [ ] CV-25. Escape clears focus and selection before it leaves fullscreen.

## Empty and filtered canvas

- [ ] CV-26. Filters that hide everything show "No nodes match your filters", with a count of what Done and Dormant hide.
- [ ] CV-27. Show Done, Show Dormant and Clear Filters each do what they say, and appear only when they apply.
- [ ] CV-28. The "Filtered" chip appears at the bottom left, and its × clears filters.

---

# 8. Filters and Communities

## Search

- [ ] FL-1. Typing suggests names and aliases. Picking one, Enter or clicking away applies it. Typing alone doesn't re-lay out the graph.
- [ ] FL-2. A bare word must begin a word: "skin" finds Skincare, not Asking.
- [ ] FL-3. A quoted word is whole: `"skin"` finds Skin Health, not Skincare.
- [ ] FL-4. A quoted phrase matches in order, across spaces and hyphens: `"skin care"` finds skin-care.
- [ ] FL-5. `OR`, in any case, splits alternatives. `skin care OR hygiene` means (skin and care) or hygiene.
- [ ] FL-6. A leading minus excludes: `skin -routine`, `-"skin care"`.
- [ ] FL-7. Aliases count as the name. Include descriptions widens the search, and the placeholder says so.
- [ ] FL-8. An applied query outlines the field. The ×, or emptying it, clears the search.

## Controls

- [ ] FL-9. Context picks several. Subcontext picks narrow only their own context: "all Health, but only STEM → Math".
- [ ] FL-10. Removing a context drops its subcontext picks.
- [ ] FL-11. Node Type picks several. Empty means All.
- [ ] FL-12. Value, Interest and Effort are two-handle ranges. Nodes with inherited ratings pass through.
- [ ] FL-13. Time takes a minimum, a maximum, or both, in a chosen unit. A container measures its unfinished inherited work.
- [ ] FL-14. A minimum above the maximum outlines both fields and filters nothing.
- [ ] FL-15. Show Done and Show Dormant reveal, and don't mark the view filtered.
- [ ] FL-16. Clear Filters resets everything, including the search and its switch.
- [ ] FL-17. Filters apply on Home, Nodes, Details and the Events neighbors, and not on Analyze.
- [ ] FL-18. On Details, a container stays even over the Time maximum, so the quick wins beneath it still show.
- [ ] FL-19. Filters are never saved. A restart opens on the whole graph.

## Communities

- [ ] FL-20. Clusters, Islands and Orphans each list their own groups, and Community starts at All.
- [ ] FL-21. Each name says what it's built around, with a context prefix when one dominates. Each shows its node count.
- [ ] FL-22. The list is ordered by importance, and capped at 20. Groups of one or two are left out, except in Orphans.
- [ ] FL-23. Orphans → All shows every orphan. The canvas empties once every node has a link, with a message that says so.
- [ ] FL-24. Selecting a community narrows Nodes, Next, Details and the nodes outside an event on Events. Each tab's chip names it.
- [ ] FL-25. Marking a node Done can regroup and rename a community. Your selection follows it, or returns to All.
- [ ] FL-26. Orphans stays right with Done hidden: a node linked only to Done nodes isn't an orphan.

---

# 9. Details

## Loading a node

- [ ] DT-1. Empty, the panel shows Suggestions: Priority Goals then Goals. Each is a card with context and a corner number.
- [ ] DT-2. Goals follow the Goals sidebar's Priority sort and show the same number.
- [ ] DT-3. They honor filters, skip Goals with no unfinished work, and skip a Goal nested in one already listed while another is available.
- [ ] DT-4. Priority Goals ignore filters.
- [ ] DT-5. Search, a suggestion, View Details, a canvas click, a subtask name and a Milestone tile each load a node.
- [ ] DT-6. Clearing the search returns to Suggestions.
- [ ] DT-7. Back and Forward step through history, and are disabled at the ends. A new selection cuts off the forward path.
- [ ] DT-8. Deleting the selected node clears the view cleanly, and history skips it.

## Node information

- [ ] DT-9. Badges show status, Now, Priority N or type, and Hard N or Soft N for a node under a Priority Goal.
- [ ] DT-10. A Goal shows a progress bar and text: percent by hours, Milestone count, time remaining.
- [ ] DT-11. Progress follows Max Depth, and counts Hard prerequisites only.
- [ ] DT-12. Inherited ratings read "Inherited". Effort hides when the node has no hours of its own.
- [ ] DT-13. Time shows the effective time, so a container shows what it inherits.
- [ ] DT-14. Edit opens the editor in place. Explain opens the modal.

## Canvas

- [ ] DT-15. The selected node has the white outline. A click re-centers the view on that node.
- [ ] DT-16. Ctrl-click only changes the selection.
- [ ] DT-17. The magnifying glass switches to Nodes and dims everything outside this view. It also clears filters.
- [ ] DT-18. Clear Focus exits.

## Local-view controls

- [ ] DT-19. Direction: Needs walks back, Supports walks forward. The table retitles, and the + hides under Supports.
- [ ] DT-20. Max Depth 1 to 5 limits the graph, table, Milestones and simulation together. The count names the depth.
- [ ] DT-21. Soft Needs off drops Soft-only nodes from all views.
- [ ] DT-22. Synergies on adds direct partners and what they need. It never chains further.
- [ ] DT-23. Show Cross-Links off drops links but never nodes.
- [ ] DT-24. Show Done mirrors the Filters switch, both ways.
- [ ] DT-25. Hide Blocked drops blocked rows, and keeps the path intact.
- [ ] DT-26. The switches sit beside whichever header is on top: Milestones if any, otherwise Subtasks. The two copies stay in step.

## Subtasks

- [ ] DT-27. The table arrives once the graph settles, with a "Loading subtasks…" line before it.
- [ ] DT-28. Scores match Home. Blocked, Done and Goal rows show a dash and sort below.
- [ ] DT-29. Relationship reads Hard, Soft or Synergy, in both directions.
- [ ] DT-30. A name click navigates. The pencil opens the editor. When the table is wider than its panel, the pencil stays at the panel's edge on hover or keyboard focus, over what scrolls beneath it.
- [ ] DT-31. **+ → New node** preselects Hard under Supports.
- [ ] DT-32. **+ → Existing node** offers nodes not already beneath it. Hard or Soft. A cycle is refused with a message in the dialog.
- [ ] DT-33. Linking one that reopens Done nodes asks first.
- [ ] DT-34. A row has no remove button. A link comes off through its menu on the canvas, or in the editor. Decide whether the table should offer it too.
- [ ] DT-35. The empty table's message fits the case: no subtasks; only Milestones; nothing under Supports.
- [ ] DT-36. The Milestones strip shows only with Milestones, Open first, each tile clickable.

## Time Simulation

- [ ] DT-37. A histogram appears with P10, P50 and P90 lines, in a unit that suits the median.
- [ ] DT-38. A bar's tooltip gives the chance of finishing by its right edge.
- [ ] DT-39. Calculating shows while it runs. A new selection cancels the old run, and the result is never stale.
- [ ] DT-40. It follows filters, Soft, Synergies, Depth and Hide Blocked.
- [ ] DT-41. Direction doesn't change it: it always looks back at what the node needs.
- [ ] DT-42. A Done node, or one whose work is all Done, says so in a sentence. Nothing beneath with hours says that too. When Max Depth, Soft Needs or a filter hides the work, the sentence says that instead.
- [ ] DT-43. A wide estimate shows a long right tail. Large views use fewer runs and stay responsive.
- [ ] DT-44. Results are stable: reselecting a node draws the same chart.

---

# 10. Goals Sidebar

- [ ] GL-1. Cards list unfinished Goals with percent done and time left. "No subtasks yet" when empty.
- [ ] GL-2. A click opens the Goal in Details, on any tab.
- [ ] GL-3. **+** starts a new Goal in a blank form.
- [ ] GL-4. Search covers names, aliases and descriptions. A card shows two lines of description. An alias match gets its own line. A description match highlights the words, with an excerpt if they'd fall below the two lines. A name match adds nothing.
- [ ] GL-5. Sort offers Priority, Time, Manual and Alphabetical. The tooltip names the current one, the menu checks it, and it survives a restart.
- [ ] GL-6. Priority shows 0 to 100, where 100 is your top unfinished Goal. A search doesn't change the numbers.
- [ ] GL-7. Time runs longest first.
- [ ] GL-8. Manual shows handles and numbers. Dragging saves. A drag under a search keeps the hidden goals' places.
- [ ] GL-9. Priority Goals pin to the top in every sort, showing their rank rather than a score. Decide whether that holds in Alphabetical.
- [ ] GL-10. The rank badge opens a popover: 1, 2, 3 or Clear.
- [ ] GL-11. Setting a rank pushes the others along. A fourth drops off the end.
- [ ] GL-12. Done frees the slot, and later ranks move up. So does changing the type.
- [ ] GL-13. A Goal whose work is all Done but isn't marked Done leaves the sidebar, unless it holds a rank. Then it stays, so you can mark it Done or clear the rank.
- [ ] GL-14. A rename or delete carries into ranks and manual order.
- [ ] GL-15. Reopening the sidebar shows the list at once, with a spinner only when something changed.
- [ ] GL-16. Priority boost: tasks under a Priority Goal rise on Home, rank 1 most.

---

# 11. Events

## Sidebar

- [ ] EV-1. The sidebar opens from its icon, and opens by itself on the Events tab when no event is selected.
- [ ] EV-2. Cards show name, description, trigger (Date, Trigger names or Manual) and a node count.
- [ ] EV-3. Sort offers Manual, Alphabetical, Trigger Type and Node Count, and survives a restart.
- [ ] EV-4. Search covers names and descriptions, with suggestions. A card shows two lines of description. A description match highlights the words, with an excerpt if they'd fall below the two lines.
- [ ] EV-5. Manual shows handles, and dragging saves. A finished event can't be dragged across the divider.
- [ ] EV-6. A fired event with nodes waiting stays: "5 nodes · 2 waking later".
- [ ] EV-7. Finished events hide behind a counted line, with a Show button that resets each launch.
- [ ] EV-8. Right-click offers Edit, Trigger Now and Delete. A triggered event hides Trigger.
- [ ] EV-9. **+** starts a new event.

## Event editor

- [ ] EV-10. The name is required. A duplicate is refused.
- [ ] EV-11. Trigger Type shows only its own fields: Manual, Date, or Node Completion.
- [ ] EV-12. Date requires a date. A date already here or past on a new event is refused, since it would fire before you could add anything.
- [ ] EV-13. Node Completion requires a node, offers dormant nodes too, and Any or All with a hint that describes the selection.
- [ ] EV-14. A new event can't watch a node already Done.
- [ ] EV-15. Saving an edit that already meets the condition fires it, and says so.
- [ ] EV-16. A node asleep in this event can't be its trigger.
- [ ] EV-17. Renaming carries nodes, triggers, and manual order.
- [ ] EV-18. Save confirms beside the button and clears. A refusal shows in the same place, in red.
- [ ] EV-19. Close (X), another card, **+** and the card menu all ask first when the form holds unsaved edits: Discard goes on, Edit stays, Save saves and goes on. A refused Save stays and says why. With nothing unsaved, they just go.
- [ ] EV-20. Delete warns that the dormant nodes go too, and only those.
- [ ] EV-21. A triggered event's panel offers Delete but not Trigger. Its trigger fields are locked. Name and description stay editable.
- [ ] EV-22. Ctrl+S saves when focus is in the event editor.

## Dormant nodes table

- [ ] EV-23. Rows show name, type, delay, wakes and hover actions. The empty message says how to add one.
- [ ] EV-24. A date event's Wakes shows a projected date, grayed. Others read "On trigger" or "2 weeks after".
- [ ] EV-25. After firing, dates turn solid. A woken node shows Awake with no actions.
- [ ] EV-26. An Add to Now flag shows as an icon.
- [ ] EV-27. **+ → New node** opens the editor already dormant here.
- [ ] EV-28. **+ → Existing nodes** offers only nodes with no event, awake and unfinished, several at once. It sets a delay and Add to Now.
- [ ] EV-29. The + hides on a triggered event, and on an unsaved one.
- [ ] EV-30. Move offers other pending events only, and says what happens to the delay.
- [ ] EV-31. Delete warns it removes the node from the graph.
- [ ] EV-32. Edit opens the one node editor.

## Firing

- [ ] EV-33. Trigger's confirmation names who wakes now, who is scheduled and when, and who joins Now.
- [ ] EV-34. The switch adds every other waking node to Now, flagged ones first, then by rank, up to the cap.
- [ ] EV-35. A date event fires on its date, even with the window left open: the event clock checks every five minutes.
- [ ] EV-36. If the app was closed that day, it fires at the next launch, and delays still count from the date.
- [ ] EV-37. Any fires on one trigger node. All waits for every one.
- [ ] EV-38. Reopening a trigger node afterward doesn't re-sleep anything.
- [ ] EV-39. Deleting a trigger node narrows the set, and tells you. Deleting the last demotes the event to Manual.
- [ ] EV-40. A narrowed set whose rest are already Done fires then.
- [ ] EV-41. A delayed node wakes on its day, with its own announcement, and joins Now if flagged and there's room.
- [ ] EV-42. A woken node that was stored Done fires events watching it.
- [ ] EV-43. Two events whose trigger nodes sleep in each other, or a longer loop, are refused and named, from saving a trigger or from adding or moving a node. Any trigger with a way out (a date, or Any with an awake node) isn't a loop. Trigger Now still breaks one saved earlier.

## Announcements

- [ ] EV-44. The Events Triggered dialog appears on any tab, at launch or the moment something fires.
- [ ] EV-45. It names the event, what woke, what's scheduled, what joined Now, and what the cap left off.
- [ ] EV-46. Dismiss, X and clicking outside all clear it. One queued meanwhile opens next. It never repeats after a restart.

## Canvas

- [ ] EV-47. It shows the event's nodes and their outside neighbors, with attached nodes marked dormant.
- [ ] EV-48. Nodes outside event, in the panel, shows or hides neighbors, and is remembered.
- [ ] EV-49. Filters narrow only the neighbors. The chip says so.
- [ ] EV-50. A click loads the editor only if it's already open.

---

# 12. Reflection

- [ ] RF-1. Marking one node Done opens the prompt, with the estimate quoted and sliders at your estimates, each with a tick for it.
- [ ] RF-2. Skip writes nothing, and the node stays in the queue. Submit writes time, ratings and notes.
- [ ] RF-3. Time fields start blank, in a unit that suits the estimate. Hour hints show under them.
- [ ] RF-4. A bracket typed back to front is put in order. A blank or zero field is no data.
- [ ] RF-5. A Milestone asks for notes only, with its own prompt.
- [ ] RF-6. Marking a Goal or a container Done opens the short form: notes only, like a Milestone's.
- [ ] RF-7. Bulk Done, a cascade and the "Mark Done?" suggestion never prompt.
- [ ] RF-8. The info icon opens the reflection wording of the rubric, separately editable.

## Hub

- [ ] RF-9. Reflect shows a count, the first few names, "+N more" and Start Reflection, or "All caught up".
- [ ] RF-10. The walkthrough shows progress, and each Submit, Skip or Don't ask again moves on.
- [ ] RF-11. Closing with X mid-way abandons the rest safely. Finishing shows "All caught up", with Done.
- [ ] RF-12. Restoring from the excluded list returns a node to the queue.
- [ ] RF-13. Excluded stays folded with its count, and hides when empty. Paging works past 20.

## History

- [ ] RF-14. Rows show estimated and actual time, Δ time and Δ ratings. Newest first.
- [ ] RF-15. Search and the context picker filter. Paging resets.
- [ ] RF-16. The sort dropdown, direction button and column headers agree. The direction tooltip names the order.
- [ ] RF-17. Missing values sort last in both directions.
- [ ] RF-18. A note icon shows a preview on hover.
- [ ] RF-19. The pencil edits, and returns to History. An unchanged Submit leaves stored hours exactly as they were.
- [ ] RF-20. Un-marking a node hides its row, and re-marking restores it.
- [ ] RF-21. Turning Reflection off stops prompts, hides the icon, and keeps the data.

---

# 13. Analyze

- [ ] AN-1. The first visit shows a spinner, then charts. Later visits are instant unless data changed. Filters never apply.
- [ ] AN-2. The overview strip shows key counts that match the graph.
- [ ] AN-3. Plan and History remember the last one. Switching doesn't flash or mis-size charts.

## Plan

- [ ] AN-4. Goals ranks like the sidebar's Priority sort. Bars are percent of hours, Hard only, with recent work brighter, and a rank badge.
- [ ] AN-5. Its gear sets rows, from 5 up, saved across restarts. The caption says Top N of M. A number below 5 is ignored, and the field reopens blank.
- [ ] AN-6. Bottlenecks ranks Open nodes by gated hours. Blocked nodes and containers are out. A gray stub shows the node's own time.
- [ ] AN-7. Nodes gating the same work share a bar. Its gear sets rows.
- [ ] AN-8. Contexts shows Value, Interest and Effort strips per area, darker for more nodes, with a tick at the mean.
- [ ] AN-9. Contexts start folded. Click opens subcontexts. Corner buttons open or close all.
- [ ] AN-10. Compare draws the all-node mean and orange or violet bars, ignoring gaps under a quarter point. It starts off each launch.
- [ ] AN-11. Hovering a cell gives the count and that rating's meaning. Hovering a tick gives the exact mean.
- [ ] AN-12. Work left shows a bar split by type on one scale. Hover gives share, mix and median.

## History

- [ ] AN-13. Throughput shows hours per bucket, stacked by context or type, with a dashed capacity line.
- [ ] AN-14. Its gear sets Granularity, Color by, Start and End. All persist.
- [ ] AN-15. Empty buckets show. The current one counts days so far. At most 24 bars, and it says so.
- [ ] AN-16. Rating Accuracy shows a row per context with four or more reflections, red left and blue right, on one scale.
- [ ] AN-17. Time Estimates by Node shows dots around y = x, colored by type. Hover names them.
- [ ] AN-18. By Context shows boxes around 1×.
- [ ] AN-19. With no history, each chart says so instead of drawing empty axes.
- [ ] AN-20. A reflection edit updates History's charts.
- [ ] AN-21. Every chart reads clearly on your displays, with no cut-off labels.

---

# 14. Settings

## The modal

- [ ] SE-1. It opens from the gear, on a fixed size, with sections on the left. Switching doesn't resize it.
- [ ] SE-2. Closing saves. So does its X. Escape and clicking outside behave as you expect.
- [ ] SE-3. A draft needing correction stays open and says what's wrong. Nothing is half-saved.
- [ ] SE-4. Closing with no changes doesn't redraw anything.

## Recommendations

- [ ] SE-5. Six profiles, each with a description. Switching changes the rankings at once.
- [ ] SE-6. Maximum Now Nodes takes 1 to 50. A blank keeps the old value.

## Editing

- [ ] SE-7. Name format offers Keep, Title Case and Sentence case. Exceptions show for Title Case only. Existing nodes are unchanged.
- [ ] SE-8. Time Estimates' four fields stay in step: 7 days a week, 4 weeks a month, 52 weeks a year. Typing in one fills the rest without drift.
- [ ] SE-9. A blank or zero rate falls back sensibly on close.
- [ ] SE-10. Hour equivalents switch shows or hides the hints in the editor at once.
- [ ] SE-11. Prompt on Done turns the prompt and the journal icon off and on without a tab switch.

## Contexts

- [ ] SE-12. One row per context, with subcontext chips and priority. Add, remove, rename and drag all work.
- [ ] SE-13. Typing never loses the caret. Bad names flag live, with one summary line.
- [ ] SE-14. Renaming a context or subcontext carries onto its nodes, including dormant ones.
- [ ] SE-15. Swapping two context names, or chaining renames, doesn't merge them.
- [ ] SE-16. Dragging a chip reorders it within its own row. It can't be dragged to another context.
- [ ] SE-17. Removing a context strikes it through with a node count and an undo, until you close.
- [ ] SE-18. Removing one with nodes opens the migration dialog: per-node pickers, Bulk apply, Apply and Cancel. Pickers offer only contexts that exist, and a subcontext can be cleared.
- [ ] SE-19. Cancel returns to the draft with your edits. There's no way to leave a node on a removed context. A node already on one has to pick a real one before it saves, and an import lists any its nodes use.
- [ ] SE-20. Priority scales rankings: 2 doubles, 0.5 halves, 0 to 10. A chip's hover gives its node count.
- [ ] SE-21. Dropdown Order changes every picker.

## Resources

- [ ] SE-22. Up to five kinds, each with a name and an optional root folder. A sixth is refused with a note.
- [ ] SE-23. Duplicate or blank names keep the modal open with a reason.
- [ ] SE-24. Removing a kind that holds links warns of the count. Undo works until close.
- [ ] SE-25. The editor, the Home dots and the menu all update to the new kinds.
- [ ] SE-26. Root folder browse works (native on desktop). Turning the switch off saves no root.

## Appearance

- [ ] SE-27. Shapes and colors per type, plus Done, Blocked and Now colors, apply on every canvas at close.
- [ ] SE-28. Hex shows beside each color. ↺ restores each group.
- [ ] SE-29. At default colors Home's bars and badges are your curated palette. Change a type color: they follow it, muted the same way its default was, and badge text stays white.

## App

- [ ] SE-30. The version shows. (desktop) The update switch persists.
- [ ] SE-31. Show graph statistics works as in HM-26 and HM-27.
- [ ] SE-32. Back up automatically persists immediately. Back up now reports the file. Open backups folder opens it.
- [ ] SE-33. An extra folder gets a copy of each new backup. A missing folder is skipped quietly.
- [ ] SE-34. Restore lists backups newest first, labeled by time and kind, and asks first.
- [ ] SE-35. Restoring reloads the page on the restored graph, and a new before-restore backup exists.
- [ ] SE-36. Export graph downloads JSON. Export database file downloads a working copy.
- [ ] SE-37. Import fills an empty graph and reloads. A non-empty graph refuses and points to Restore.
- [ ] SE-38. A wrong file, a newer export or a damaged export refuses and changes nothing.
- [ ] SE-39. After an import, root folders are empty and the extra backup folder is this computer's.
- [ ] SE-40. No in-app way to reach diagnostics, the bug report link, third-party notices or Check Now yet. Add Settings > About for the first release.

---

# 15. Keyboard

- [ ] KB-1. Ctrl+/ opens the shortcut reference. Its list is complete and correct. Escape closes it and returns focus.
- [ ] KB-2. Tab shows a visible outline everywhere, and skips closed sidebars.
- [ ] KB-3. Left, Right, Home and End move along tabs. Enter opens a tab and moves into it: first Now card, Nodes graph, Details search, Events search, Analyze's Plan.
- [ ] KB-4. Opening a sidebar by keyboard moves focus into it. Tab stays inside until Escape or Close.
- [ ] KB-5. Escape closes the innermost thing first, and returns focus to its opener. An open dropdown closes with no change.
- [ ] KB-6. Cards in a list share one Tab stop. Arrows, Home and End browse.
- [ ] KB-7. In Goals and Events, Down from search enters the list, and Up from the top returns.
- [ ] KB-8. On Home, Tab moves between Now cards, Down drops to Next, and Up from its first row returns.
- [ ] KB-9. Alt+Enter or the Menu key opens a card's or row's menu. Arrows, Enter, Right and Left work inside, including submenus.
- [ ] KB-10. Alt+arrows reorder Now cards and manual goals, events, contexts and subcontexts.
- [ ] KB-11. On a graph: arrows move toward nodes, Page Up/Down browse by name, Home/End go to the ends, Enter selects, Shift+Enter adds, Alt+Enter opens the menu.
- [ ] KB-12. + and − zoom, and 0 fits. A blue halo marks focus, and it pans only when needed. The focused node's name and status are announced.
- [ ] KB-13. Delete on the Nodes graph asks. Escape clears focus and selection first.
- [ ] KB-14. Arrows resize dividers. Shift takes bigger steps. Home and End go to limits.
- [ ] KB-15. Enter on an Analyze gear opens its settings with focus inside.
- [ ] KB-16. Modals trap focus and return it on close.

---

# 16. Desktop App

All (desktop).

- [ ] DK-1. The installer runs without admin rights, offers a desktop shortcut, and the icon is right.
- [ ] DK-2. The window opens maximized, with the toolbar as the title bar and drag on empty toolbar space.
- [ ] DK-3. Window buttons dim with a modal's backdrop on Windows.
- [ ] DK-4. External links open in your browser. The window never navigates away.
- [ ] DK-5. Closing shuts the server cleanly, with no leftover process.
- [ ] DK-6. A second launch focuses the first window.
- [ ] DK-7. A killed page offers Reload or Quit. A killed server says it stopped.
- [ ] DK-8. An update check runs 15 seconds after launch when on, and never when off.
- [ ] DK-9. Windows and AppImage download and install on the next quit. macOS and .deb offer the download page.
- [ ] DK-10. F12 or Ctrl+Shift+I opens DevTools in sandbox and development runs. A packaged build has none, and no menu item for it.
- [ ] DK-11. Native file and folder pickers appear on top of the window.
- [ ] DK-12. macOS: Cmd+C and Cmd+V work in fields, and the menu is sensible. Linux: native frame.
- [ ] DK-13. Uninstalling leaves your data, and a reinstall picks it up.

---

# 17. Hidden Machinery

You can't click these, so check their effects. Each runs without being asked.

## Status

- [ ] HD-1. Marking a node Done unblocks dependents whose other prerequisites are Done.
- [ ] HD-2. Reopening a prerequisite re-blocks Done nodes after it, except Milestones and Goals.
- [ ] HD-3. Goals never turn Blocked. A Done Milestone never re-blocks.
- [ ] HD-4. Finishing a Goal's last Hard child suggests "Mark Done?", for Goals and inherited-time containers but never Milestones. It never marks one itself.
- [ ] HD-5. Dismissing leaves it open, with no repeat until another completion.
- [ ] HD-6. A chained suggestion follows when marking one completes another's prerequisites.

## Launch repairs

- [ ] HD-7. Statuses are recomputed from prerequisites, repairing drift and logging it.
- [ ] HD-8. Synergy links are stored in a canonical order.
- [ ] HD-9. Priority ranks held by non-Goals or finished Goals are cleared.
- [ ] HD-10. Nodes already woken by an event are made awake.
- [ ] HD-11. Events whose conditions already hold are fired.

## Scoring

Read [scoring.md](scoring.md) alongside these.

- [ ] HD-12. A higher Value or Interest raises a score. Higher Effort or Time lowers it.
- [ ] HD-13. Finishing a prerequisite changes what's ranked next, as you'd expect.
- [ ] HD-14. Value flows forward along links. Hard counts more than Soft, and Milestones pass it on free.
- [ ] HD-15. Synergy reinforces, and is bounded: many partners approach twice one Done partner's effect.
- [ ] HD-16. A Priority Goal lifts its subtree. Rank 1 lifts most.
- [ ] HD-17. Context priority scales its tasks.
- [ ] HD-18. Each profile visibly changes the ranking in the direction its description says.
- [ ] HD-19. Inherited nodes behave as documented: no own value, and no recommendation when time is inherited.
- [ ] HD-20. Scores update after an edit and stay cached otherwise. A cosmetic edit doesn't reorder anything.
- [ ] HD-21. Goal ranking uses the average worth of remaining Hard work, so size alone doesn't win.

## Time

Read [time.md](time.md) alongside these.

- [ ] HD-22. One input is used as is. Two imply a middle. Three use Swanson's rule. Each shows up in the node's time.
- [ ] HD-23. A habit's hours follow duration × days × minutes.
- [ ] HD-24. Inherited time sums unfinished Hard prerequisites only.
- [ ] HD-25. Changing hour rates changes displayed units, not stored hours.

## Data safety

- [ ] HD-26. A daily backup appears at launch, and once a day while left open, only when something changed.
- [ ] HD-27. Thirty daily copies are kept, plus ten of each other kind.
- [ ] HD-28. A failed save changes nothing: a save is one transaction, including its links and dormancy.
- [ ] HD-29. Deleting a node records it in the ledger. History survives a rename.
- [ ] HD-30. The server takes one instance per database, and a crash releases the lock.

## Security and privacy

- [ ] HD-31. The server listens on 127.0.0.1 only.
- [ ] HD-32. Requests without the launch token are refused. A stale link says it's out of date.
- [ ] HD-33. Another site's page can't call the app: Host and Origin are checked.
- [ ] HD-34. The app makes no outside requests at all, apart from the update check. Fonts and icons are local.
- [ ] HD-35. Logs name no personal data beyond node names. Decide whether that's acceptable.
- [ ] HD-36. An imported file can't run anything or inject markup, and its risky links still ask first.
- [ ] HD-37. Watch for "Callback failed: the server did not respond", which shouldn't appear. Automated driving caused it now and then, never real use. If it appears by hand, it's a bug.

---

# 18. Documents and Website

- [ ] DC-1. [README](../README.md) reads as you want, and the download link works.
- [ ] DC-2. [features.md](features.md) matches the app as you find it. Mark anything out of date.
- [ ] DC-3. [modeling.md](modeling.md), [scoring.md](scoring.md) and [time.md](time.md) match too.
- [ ] DC-4. [install](user/install.md), [privacy](user/privacy.md) and [troubleshooting](user/troubleshooting.md) are true.
- [ ] DC-5. Screenshots in docs/images match the current look.
- [ ] DC-6. The Website project's landing page, 404 page and download link work and say what you want.
- [ ] DC-7. Third-party notices ship with each build.

---

# What the first pass found

## Fixed in the first pass

| Items | What was wrong | What it does now |
|---|---|---|
| ED-106 | On a freshly loaded page, what you typed into the editor could be closed or replaced with no question. That form had nothing to compare itself with. | It has the same baseline as every later form, so closing or a canvas click asks. |
| ED-104, ED-105 | Unsaved edits left behind Goals or Events could vanish silently. A canvas click replaced them, an empty click blanked them, and Edit and the **+** menus overwrote them. | A canvas click leaves them alone. Anything that opens the editor on something else asks first. |
| ED-100, GL-3 | The Goals sidebar's **+** only set the type. With a node loaded, that turned the node into a Goal, under its own name, ready to be saved that way. | It starts a blank Goal, and asks first if there are unsaved edits. |
| ED-88 | Save with no name closed the editor and dropped everything, unless you had typed a description or moved a rating. | It asks for the name whenever the form holds anything. |
| ED-57 | Save started enabled on the form a fresh page opens with, though every other blank form waits for an estimate. | It starts disabled there too. |
| ED-17 | The "Possible duplicate" warning showed once. It stayed hidden on every later blur with the same answer. | It shows each time. |
| ED-59 | Changing units rounded to two decimals. 100 hours became 0.1 years, then 104 hours on the way back. A few hours became 0 years. | It keeps four significant digits. 100 hours comes back as 100. |
| ED-83 | A link that wouldn't open showed in success green. A missing file's message was only its path. | It opens the error dialog and says there is no file there. |
| ED-38 | The excluded note said to restore in Settings. Restoring lives in Reflection. | It names Reflection. |
| DT-42 | With Max Depth, Soft Needs or a filter hiding all the work, Time Simulation said no work leads into the node. | It says the work is outside this view, and what could be hiding it. |
| AN-5, AN-7 | The rows fields took multiples of 5 only. Typing 7 did nothing, and the field came back blank. | Any whole number from 5 up works. |
| HM-4 | With a cap of one, the toast said "1 Now nodes". | It counts properly. |
| EV-12 | A new event dated today or earlier said Saved, then fired empty on the next click. | It's refused, and says why. |
| EV-18 | A refused event save read in success green. | It's red. |
| EV-23 | The empty table said to click "Add Node", which is on no button. | It names the **+**. |
| ST-14 | Getting Started said to choose "Now". The menu says Add to Now. | It says Add to Now. |
| SH-6, SE-11 | The journal icon kept its old state after Settings until you switched tabs. | It follows the setting at once. |
| MN-3 | View Details on a dormant node loaded nothing on a fresh page. | Details' picker holds dormant nodes, so it loads. |
| HM-27 | The statistics caption ignored its switch, even after a reload. Its counts never moved after launch. | The switch hides and shows it at once. The counts follow the graph. |
| DC-2, DC-4 | The docs described an × and Remove Subtask modal, a Locate button on Details, an Open Events Sidebar button, a gray arrow for aliases, a chart called Rating Drift and a Help command. None exists. One sentence in the shortcuts section was broken. | They describe the app as it is, and mention the event date rule. |

The caption's node count means nodes left to do, which is what it already showed at launch.

## Decisions for you

You went through these on 2026-11-01. Items marked Fix were then changed, with tests, and driven in a real browser where they show there. Check them again in your manual pass.

| Item | Decision | What it means |
|---|---|---|
| ED-31 | Fix | The editor's Now switch waits for Save, and Revert undoes it. The menu, Now cards and dragging still act at once, since they have no Save. |
| ED-48 | Fix | A node its event woke can sleep again. Its new event replaces the old row, so the old event no longer lists it. |
| ED-21 | Fix | A node's aliases show by themselves when it has any. |
| ED-24 | Fix | An alias can't match another node's name, and a name can't match another node's alias. |
| ED-52 | Fix | The Ratings Reference comes back after its table's Save or Cancel. |
| ED-104 | Keep | Opening Goals or Events slides the editor away with your unsaved edits, without asking. Nothing marks a waiting draft yet. See whether you miss one in your manual pass. |
| HM-19 | Fix | Next's row count survives a restart, can be typed, and its buttons stay gray after a click. |
| HM-25, FL-24 | Fix | Community and Orphans narrow Next, Details and Events too, and show in their chips. |
| SH-25 | Later | Left sidebars still cover Home. This gets its own pass. It was tried once and dropped, so start by reading the sidebar commits. |
| MN-11 | Fix | Add to Event is hidden for nodes that can't join one, and counts only those that can. |
| EX-14 | Fix | Focus zooms toward the route, but keeps enough of the graph around it for context. |
| EX-17 | Fix | Focus Top n clears filters, as Details' Focus does. |
| DT-30 | Fix | The Subtasks pencil stays at the panel's edge however far the table scrolls. It still appears only on hover or keyboard focus. |
| DT-34 | Keep | Subtasks rows have no remove button. An earlier x was unclear about whether it removed the link or the node. |
| GL-4, EV-4 | Fix | Every search across names covers aliases. Goals search also covers descriptions. Goal and event cards show two-line descriptions. A match the card doesn't show gets one extra line, and matching words in a description are highlighted. |
| GL-9 | Keep | Priority Goals stay pinned in every sort. |
| GL-13 | Fix | A Goal holding a rank stays in the sidebar when its work is all Done, until you mark it Done or clear the rank. |
| EV-19 | Fix | Leaving an event with unsaved edits asks first. |
| EV-21 | Fix | A triggered event's panel offers Delete. Its trigger fields lock. Name and description stay editable. |
| EV-43 | Fix | A loop of events that wake each other's triggers is refused, at any length. Loops already saved stay, and Trigger Now still works on them. |
| RF-6 | Fix | Marking a Goal or a container Done opens a short form rather than the full one. |
| SE-19 | Fix | A node can't keep a context that no longer exists. The migration dialog loses Skip and Keep existing, and a node already on one has to pick a real one before it saves. |
| SE-29 | Fix | Home's bars and badges keep your curated palette at the default colors. A changed type color gets a muted version with the same perceptual treatment. Badge text is always white. |
| SE-40 | At release | Add Settings > About for the first release. The update check and the bug form already exist, and `skilltree/features/settings/about.py` stays for it. |
| DK-10 | Fix | DevTools is off in packaged builds. Sandbox and development runs keep it. |
| HD-37 | Closed | `ERR_NO_BUFFER_SPACE` has only appeared under automated testing, never in real use. Treat it as a bug if "the server did not respond" ever shows up by hand. |

All the code that did nothing is removed: `ctx-obsidian-path-store`, `ctx-drive-path-store`, the `edge-resources` store, `details-filters-sidebar` and its `details-filter-*` controls, `details-simulate-trigger-input`, `event-status-badge`.

## What the first pass couldn't check

Every item in sections 1 to 15 and 17 was exercised in a real browser against a real server, apart from these:

- The desktop app (section 16, and every "(desktop)" item). The shell's unit tests pass, but no Electron window was opened. Its messages and exit codes were checked from the server's side. DK-10 needs a packaged build to see.
- Links really opening (ED-79, ED-81) and native pickers (ED-80, SE-26's browse button). The questions and refusals were checked, but nothing was launched on your computer.
- A tooltip under a still pointer (SH-15). Headless Chrome sends no events when something slides under the pointer.
- How it feels: animation, tooltip timing and canvas gestures at 240 Hz, and the look at 4K (SH-22, AN-21). The browser ran at 60 Hz in a 1600×1000 window.
- Whether the rankings seem right to you (HD-13, HD-18, HD-21). Each effect was seen moving the right way, on throwaway data, and the test suite covers the math. HD-21 rests on the suite alone.
- Time passing (EV-35, EV-36, HD-26). The dates were edited in a copy, and the event clock was ticked by hand, rather than waiting for them.
- Reading the documents through (DC-1 to DC-4). Every bold term in them was looked up in the code, which is how the stale ones above were found. That doesn't prove the prose is right.
- The website, the screenshots in docs/images and the third-party notices in a build (DC-5 to DC-7).

A pass also doesn't answer the third question at the top of this document. Only you can say whether it's what you want.
