---
name: <slug>              
description: "<One-line description of the skill, used in the generated docstring.>"      
version: "0.1"            
kind: scorer      
# kind options: score | tracer | runner

# env_vars: environment variables the adapter reads from os.environ.
# Remove this block if the adapter has no env-vars dependencies.
env_vars:                  
  - name: MY_SERVICE_API_KEY      
    required: true         
    description: "API Key for the external service."
  - name: MY_SERVICE_HOST      
    required: false         
    description: "Base URL override (uses the service default if unset)."

# parameters: constructor fields for the generated adapter class.
# Remove this block if the adapter needs no configuration beyond env-vars.
parameters:               
  - name: model_id        
    type: str              
    required: true         
    description: "Model identifier used by the judge."
  - name: rubric_id
    type: str
    description: "Rubric identifier (used as cache key component)."
    required: true
  - name: timeout
    type: float
    required: false
    default: "30.0"
    description: "Request timeout in seconds."
---

## What this skill does

<!-- Required. Describe what the adapter does in plain English.
     This text is embedded in the generated module docstring and 
     the factory.py hint. Be specific about the external system,
     protocol, and data flow. -->

<!-- Describe the adapter here -->

## Implementation notes 

<!-- Optional but recommended. Describe any non-obvious implementation constraints, 
     authentication patterns, response parsing logic, or whatifd cardinal-rule 
     reminders specific to this adapter. 
     This section is included verbatim in the generated docstring. -->

### Authentication

<!-- How does the adapter authenticate? Environment variables? Header?
     Example: `os.environ.get("MY_SERVICE_API_KEY")` passed to the SDK constructor. -->

### Scoring response format

<!-- For scorers: what does the judge model return, and how is the float score
     (0.0-1.0) extracted? 
     Example: parse JSON block `{"score": 0.7, "rationale": "..."}`  from the 
     model's text response. -->

### Cardinal #5 - Sensitive wrapping

<!-- Remind the implementor where Sensitive[T] wrapping is required.
     At minimum, user_message, original_response, any rationale text. -->

Wrap user content before returning it:
```python
from whatifd.types.sensitive import Sensitive
rationale = Sensitive(value=raw_rationale, classification="user_content")
```

### Error handling (cardinal #1)

<!-- What errors can the external API raise? How should they map to whatifd's 
     typed errors?
     For scorers: a scoring failure returns JudgeResult(score=None, ...)
     (not an exception). For construction failures: raise AdapterFactoryError 
     from the factory.py dispatch branch. -->
