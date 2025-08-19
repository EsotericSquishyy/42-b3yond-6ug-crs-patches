package org.b3yond.model;

public class Task {
    private String diff;
    private String focus;
    private String fuzzing_tooling;
    private String project_name;
    private String[] repo;
    private String task_id;
    private String task_type;

    // Getters and setters
    public String getDiff() { return diff; }
    public void setDiff(String diff) { this.diff = diff; }
    
    public String getFocus() { return focus; }
    public void setFocus(String focus) { this.focus = focus; }
    
    public String getFuzzing_tooling() { return fuzzing_tooling; }
    public void setFuzzing_tooling(String fuzzing_tooling) { this.fuzzing_tooling = fuzzing_tooling; }
    
    public String getProject_name() { return project_name; }
    public void setProject_name(String project_name) { this.project_name = project_name; }
    
    public String[] getRepo() { return repo; }
    public void setRepo(String[] repo) { this.repo = repo; }
    
    public String getTask_id() { return task_id; }
    public void setTask_id(String task_id) { this.task_id = task_id; }
    
    public String getTask_type() { return task_type; }
    public void setTask_type(String task_type) { this.task_type = task_type; }
}
