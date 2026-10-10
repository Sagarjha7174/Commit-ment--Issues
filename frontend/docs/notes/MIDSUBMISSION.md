# Green Home Score - Frontend Mid-Submission Report

## 1. Overview of Frontend Implementation
For this mid-submission, the focus has been on establishing a robust, modern frontend architecture and building out the core user interface for the **Green Home Score** application. The application provides homeowners in York with personalized retrofit recommendations based on energy models.

## 2. Technology Stack & Architecture
- **Framework & Build Tool:** React 19 + Vite 8
- **Language:** TypeScript for type safety and scalability
- **Routing:** `react-router-dom` (v7) managing three core routes
- **Styling:** Vanilla CSS with a global design system using CSS variables. The palette is intentionally designed to feel authoritative yet accessible, using a cream background, ink text, and red accents, paired with *DM Serif Display* and *Manrope* fonts.
- **Icons:** `lucide-react` for lightweight, scalable iconography.
- **State & Data Fetching (Planned):** TanStack Query is installed and selected as the data fetching library for when backend integration begins.

## 3. Completed Milestones
### A. Application Structure & Routing
- Set up the main entry point (`src/main.tsx`) and application shell (`src/App.tsx`).
- Implemented a persistent top navigation bar (`TopNav.tsx`) to switch seamlessly between the three core views.

### B. Core Views Developed (with Mock Data)
The UI has been fully designed and built out using mock data to demonstrate the intended user experience while the backend API is being finalized:

1. **My Home Dashboard (`/`)**: 
   - Displays property diagnosis, EPC ratings, and a detailed energy balance (Gas, Electricity, Carbon). 
   - Features a "Scenario Lab" allowing users to toggle interventions (like Loft Insulation or Air Source Heat Pumps) and see real-time updates to costs and carbon savings via mock browser-side calculations.
   - Includes a "Retrofit Decision Studio" to compare different retrofit packages (Lowest Cost, Largest Carbon Cut, Best Carbon per £).

2. **Homes Needing Help (`/homes-needing-help`)**:
   - A searchable, interactive opportunity table.
   - Filters mock data of properties in York rated "Poor" or "Very Poor".
   - Features visual EPC tags and status indicators to help quickly identify high-priority properties.

3. **Method & Evidence (`/method-evidence`)**:
   - A dedicated transparency page detailing data provenance (e.g., NEED 2026 Model, York Open Data).
   - Showcases model performance metrics (e.g., ±8% margin of error) and the rigorous validation checks applied to recommendations (like Conservation Area constraints).

### C. Engineering & Auditing
- Successfully configured build and linting pipelines (`npm run build`, `npm run lint`).
- Conducted a comprehensive **Frontend Lead Audit** to map out the exact integration points required from the backend (Pydantic schemas mapping, API routes, units of measurement, and error handling formats).

## 4. Next Steps (Post Mid-Submission)
1. **API Integration:** Replace all browser-side calculations and hardcoded mock data with TanStack Query hooks pulling from the backend engine.
2. **Type Safety:** Introduce `src/api/types.ts` to mirror the Python Pydantic schemas (e.g., `ScenarioRequest`, `PackageResult`) for strict contract enforcement.
3. **Mock Mode:** Create a robust local mock service based on "Golden JSON" fixtures provided by the backend to unblock frontend development while the Python server routes are being completed.
