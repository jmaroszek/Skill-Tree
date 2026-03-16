---
aliases:
- Skill Tree
tags:
- Temp
---
## Overview
I want to create an app that helps me prioritize tasks, goals, and projects. I am focused on learning projects and major life milestones. Thus, the primary feature I am interested in understanding is the relationship among tasks. I want to know what tasks must be completed before others (dependencies), which tasks synergize well with each other, and which are completely independent. I plan to create a visualization that helps me understand these relationships among tasks, and an algorithm that helps me choose the next thing I want to work on based on various attributes such as value, effort, and interest. 
## Graph Structure
I believe that a graph data structure will be the best way to approach this project. 
### Node Types
I want my app to work with various types of nodes. Below, I provide a description of each node type. In the next section, I will describe the attributes associated with each node.

| Type     | Description                                                                                        |
| -------- | -------------------------------------------------------------------------------------------------- |
| Topic    | A general topic that I wish to learn about                                                         |
| Goal     | A specific outcome that I want to achieve                                                          |
| Skill    | An ability I want to learn                                                                         |
| Habit    | A repeated behavior I want to establish                                                            |
| Resource | A resource, such as a book or website, that I believe will be useful for learning a topic or skill |
### Node Attributes

| Attribute   | Description                                                                                                   | Data Type   | Range                                                                                          | Nullable |
| ----------- | ------------------------------------------------------------------------------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------- | -------- |
| Name        | A unique identifier for the node. Must be unique                                                              | String      | NA                                                                                             | No       |
| Type        | The node type described in the table under the section "Node Types"                                           | Categorical | \[Goal, Topic, Skill, Habit, Resource]                                                         | No       |
| Description | A textual description of what I mean by this node                                                             | String      | NA or                                                                                          | No       |
| Value       | How valuable I think it would be to complete this node                                                        | Int         | 1-10                                                                                           | No       |
| Time        | Time estimate in hours                                                                                        | Int         | (0, inf)                                                                                       | No       |
| Interest    | How much I want to do this node                                                                               | Int         | 1-10                                                                                           | No       |
| Effort      | How challenging I expect the node to be                                                                       | Categorical | \[Easy, Medium, Hard]. For calculations in the algorithm, map these to the integers \[1, 2, 3] | No       |
| Competence  | Describes how good I want to be at this particular node. It uses a personal classification system I developed | Categorical | \[Reciter, Processor, Thinker, Creator, Master, Innovator]                                     | Yes      |
| Context     | The life area that this node belongs to                                                                       | Categorical | \[Mind, Body, Social]                                                                          | Yes      |
| Subcontext  | I have subcategories for each context. See the table under the header "Subcontexts" for details               | NA          | NA                                                                                             | Yes      |
| Status      | Describes the state of this node based on its relationship to other nodes                                     | Categorical | \[Open, In Progress, Blocked, Done]                                                            | No       |
### Subcontexts
This section describes the subcategories for each of the "main" contexts: Mind, Body, Social, and Action. All are categorical variables.

| Context | Subcontexts                                        |
| ------- | -------------------------------------------------- |
| Mind    | Rational, Sensory, Judgment, Creative, Pragmatic   |
| Body    | Stress, Rhythms, Nutrition, Exercise               |
| Social  | Relationships, Communication, Psychology, Morality |
### Node Relationships
This section describes the types of relationships that can occur between nodes.

| Relationship | Relationship Type | Description                                                                                                                        |
| ------------ | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Needs        | Directed          | Node A $\rightarrow$ Node B. Node A is a prerequisite to start node B. If Node A is not "Done," Node B's status must be "Blocked." |
| Helps        | Undirected        | Node A $\leftrightarrow$ Node C. A synergistic relationship where completing one node makes the other easier or more valuable.     |
| Resource     | Directed          | Resource Node $\rightarrow$ Node A. Resource nodes support the completion of target nodes.                                         |
### Node Methods

| Method           | Description                                                                                                                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Search           | Search nodes by name or attribute, accounting for filters                                                                                                                                                            |
| Add              | Add a node with certain attributes and relations                                                                                                                                                                     |
| Delete           | Delete a node by name                                                                                                                                                                                                |
| Edit             | Update an existing node (attributes and edges)                                                                                                                                                                       |
| Filter           | Filter nodes by their attributes. The important attributes to consider are type, value, time, interest, effort, context, and subcontext.                                                                             |
| Cycle Detection  | Validate new `Needs` edges before adding them to ensure the DAG remains acyclic.                                                                                                                                     |
| Toggle Done      | Change the state of the note to done (complete) or open (not done). Note: 'Done' is not a permanent state. I can toggle a node back to 'Open', which is especially useful for Habit nodes if I fall out of practice. |
| State management | When a node is completed, the system must automatically update the status of any dependent nodes from "Blocked" to "Open." Similarly, if a node needs another, its status must be marked as "Blocked"                |
## App Features
### Visualizations
#### Graph View
I want an interactive network visualization that shows the structure of the graph. Please use a library well-suited for interactive Python GUIs (such as `Pyvis` , `Plotly` , or `Dash` ). The visualization must adhere to the following rules:
- **Layout:** Because the `Needs` relationships form a DAG, default to a **hierarchical layout** (e.g., top-to-bottom or left-to-right) so the flow of prerequisites is immediately obvious.
- **Node Styling:**
    - **Labels:** All nodes must be labeled clearly with their `Name`.
    - **Color by Status:** Use colors to represent `Status` (e.g., Red = Blocked, Blue = Open, Yellow = In Progress, Green = Done).
    - **Shape by Type:** Use different shapes to represent `Type` (e.g., Start = Goal, Circle = Topic, Triangle = Skill, Diamond = Habit, Pentagon = Resource).
- **Edge Styling:** 
	- **Needs:** Solid lines with directional arrows ( $\rightarrow$ ).
    - **Helps:** bi-directional arrows to show synergy ($\leftrightarrow$).
    - **Resource:** Dotted lines with directional arrows pointing to the target node.
- **Interactivity:**
    - **Tooltips:** Hovering over a node should reveal a tooltip displaying its `Type`, `Status`, `Context`, `Value`, `Effort`, and `Priority Score`.
    - **Selection:** Clicking a node should select it, populating its data into the "Node Editor" and "Suggestion Algorithm" views.
- **Filtering:** The UI must include dropdowns, checkboxes, or sliders to filter the graph dynamically (e.g., "Hide 'Done' nodes", "Only show 'Mind' context", or "Only show nodes with Value > 5").
#### Node Editor
- **Layout:** Place the Node Editor in a persistent sidebar or a split-pane view next to the Graph View, so I can edit a node while looking at the graph.
- **Input Types:** The form must automatically use the correct input widgets based on the Data Type:
    - _Strings:_ Text input fields.
    - _Categorical:_ Dropdown menus (to prevent typos).
    - _Integers (Value, Interest, Time):_ Sliders or number spin-boxes.
- **Relationship Mapping:** To add "Needs" or "Helps" edges, use a searchable, multi-select dropdown menu populated with the names of all existing nodes in the database.
- **Contextual Fields:** The "Subcontext" dropdown should dynamically update its options based on what is selected in the "Context" dropdown.
- Do not store the `Priority Score` as a column in the database. It must be a computed property calculated at runtime by the algorithm so it updates dynamically when weights or graph states change.
### Suggestion Algorithm
#### Primary Algorithm
The app needs an extensible algorithm engine to suggest the next node to work on. It must only evaluate nodes with a status of "Open" or "In Progress" (ignoring "Blocked" or "Done" nodes).

Implement a baseline scoring algorithm using this logic:

$$\text{Priority Score} = \left( \frac{\text{Value} \times \text{Interest}}{\text{Time} \times \text{Effort Numeric}} \right) + (W_n \times N) + (W_h \times H)$$
Where:
- $N$ = The number of blocked nodes this task will directly unlock.
- $H$ = The number of synergistic "Helps" connections this node has to other active nodes.
- $W_n$ and $W_h$ = Adjustable weight variables (default them to 2.0 and 1.0 respectively).

Comments
- **Display Output:** The algorithm should output its results in a clearly formatted "Top 5 Recommended Tasks" list or table, sorted by the highest `Priority Score` .
- **Filter Awareness:** The algorithm must dynamically respect the active filters applied to the Graph View. If I filter the graph to only show "Mind" context nodes, the algorithm should _only_ calculate and suggest from that filtered pool.
- **Score Transparency:** In the UI output, show the final Priority Score next to the suggested node
- **Trigger:** The algorithm should auto-calculate whenever the graph is updated or a filter is changed
#### Dependency Traversal View
For a selected Goal node, traverse the DAG backward to list all incomplete prerequisite chains required to achieve it.
## Technical Specifications
### Requirements
- Use **Python** for the core logic.
- Create a lightweight, local GUI (e.g., **Streamlit** or **Custom Dash App**).
- Store data locally using **SQLite**. Use a normalized schema with separate tables for `Nodes` and `Edges`.
- **Computed Properties:** Do **not** store `Priority Score` in the database; it must be calculated at runtime.
- **Integrity:** Implement **Cycle Detection** and prevent self-dependencies.
### State Management
- Whenever a node is marked "Done" or "Open," trigger a recursive update to refresh the `Status` of all connected nodes.
### Coding Style
- I prefer **Object-Oriented Programming**.
- Define a `Node` class and a `GraphManager` class to handle logic.
- Use small, isolated functions with descriptive names and concise docstrings

### File Organization
- Create an environment.yml file for all libraries that are not in the base anaconda distribution
- The data for the nodes and edges should not be tracked by github
