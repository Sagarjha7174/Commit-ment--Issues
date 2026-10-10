import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="page page-head">
      <p className="kicker"><b>404</b>Not found</p>
      <h1 className="page-title">This page does not exist</h1>
      <p className="lead"><Link to="/home">Go to My Home</Link> or <Link to="/homes-needing-help">browse homes needing help</Link>.</p>
    </div>
  );
}
